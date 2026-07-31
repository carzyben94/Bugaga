# bot.py - с пошаговой верификацией
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
# СЕЛЕКТОРЫ
# ============================================================

TEXTAREA_SELECTOR = "div.message-input-wrapper > div.message-input-container:nth-of-type(2) > div > div.message-input-container-area > textarea.message-input-textarea"
SEND_BUTTON_SELECTOR = ".message-input-right-button-send"

# ============================================================
# BROWSER HARNESS
# ============================================================

class BrowserHarness:
    def __init__(self, cdp_url="http://localhost:9222"):
        self.cdp_url = cdp_url
        self.ws_url = None
        self.step_log = []
    
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
    
    async def verify_text_set(self, selector, expected_text):
        """Проверить, установился ли текст"""
        js = f"""
        (function() {{
            var el = document.querySelector('{selector}');
            if (!el) return {{success: false, error: 'Элемент не найден'}};
            return {{
                success: true,
                value: el.value,
                matches: el.value === '{expected_text.replace("'", "\\'")}'
            }};
        }})()
        """
        return await self.evaluate(js)
    
    async def verify_send_button_clicked(self):
        """Проверить, нажалась ли кнопка отправки (поле очистилось)"""
        js = f"""
        (function() {{
            var el = document.querySelector('{TEXTAREA_SELECTOR}');
            if (!el) return {{success: false, error: 'Поле не найдено'}};
            // Если поле пустое - значит сообщение отправилось
            return {{
                success: true,
                is_empty: el.value === '' || el.value === null,
                value: el.value
            }};
        }})()
        """
        return await self.evaluate(js)
    
    async def get_qwen_response(self):
        """Получить ответ"""
        js = """
        (function() {
            var selectors = [
                '.qwen-markdown-text',
                '.message-content',
                '#chat-message-container',
                '[class*="message"]'
            ];
            
            var allTexts = [];
            for (var s of selectors) {
                var els = document.querySelectorAll(s);
                for (var i = 0; i < els.length; i++) {
                    var text = (els[i].textContent || '').trim();
                    if (text && text.length > 10) {
                        allTexts.push(text);
                    }
                }
            }
            
            // Фильтруем системные
            var systemPatterns = [
                'AutoChoose', 'Get Started', 'Please enter',
                'Что бы вы хотели', 'Log in', 'Sign up',
                'Скачать приложение', 'Войти', 'Завершено размышление',
                'Thinking completed', 'Выберите', 'Ваш выбор',
                'Используя Qwen Studio', 'Пользовательские условия',
                'Политика конфиденциальности', 'Сообщить'
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
            
            if (filtered.length > 0) {
                filtered.sort(function(a, b) { return b.length - a.length; });
                return filtered[0];
            }
            return null;
        })()
        """
        return await self.evaluate(js)
    
    async def ask_qwen(self, question):
        """Запрос к Qwen с пошаговой верификацией"""
        self.step_log = []
        
        try:
            # ШАГ 1: Переход на сайт
            logger.info("📌 ШАГ 1: Переход на chat.qwen.ai...")
            await self.navigate("https://chat.qwen.ai/")
            await self.wait_for_load(5)
            self.step_log.append("✅ ШАГ 1: Страница загружена")
            
            if COOKIES:
                await self.set_cookies(COOKIES)
                await self.wait_for_load(2)
                await self.navigate("https://chat.qwen.ai/")
                await self.wait_for_load(5)
                self.step_log.append(f"✅ ШАГ 1.1: Установлено {len(COOKIES)} кук")
            
            # ШАГ 2: Ввод текста
            logger.info(f"📌 ШАГ 2: Ввод текста: {question[:30]}...")
            
            # Клик по полю
            js_click = f"""
            (function() {{
                var el = document.querySelector('{TEXTAREA_SELECTOR}');
                if (!el) return false;
                el.focus();
                el.click();
                return true;
            }})()
            """
            await self.evaluate(js_click)
            await self.wait_for_load(0.3)
            
            # Установка текста
            js = f"""
            (function() {{
                var el = document.querySelector('{TEXTAREA_SELECTOR}');
                if (!el) return {{success: false, error: 'Элемент не найден'}};
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
                return None, "Не удалось ввести текст", self.step_log
            
            # ВЕРИФИКАЦИЯ: проверяем что текст установился
            verify = await self.verify_text_set(TEXTAREA_SELECTOR, question)
            logger.info(f"🔍 Верификация ввода: {verify}")
            
            if not verify.get('success'):
                return None, "Ошибка проверки ввода", self.step_log
            
            if not verify.get('matches'):
                self.step_log.append(f"❌ ШАГ 2: Текст не установился! Ожидалось: '{question}', Получено: '{verify.get('value')}'")
                return None, f"Текст не установился. Ожидалось: '{question}', Получено: '{verify.get('value')}'", self.step_log
            
            self.step_log.append(f"✅ ШАГ 2: Текст установлен: '{verify.get('value')}'")
            await self.wait_for_load(0.5)
            
            # ШАГ 3: Нажатие кнопки отправки
            logger.info("📌 ШАГ 3: Нажатие кнопки отправки...")
            
            # Находим кнопку
            js_btn = f"""
            (function() {{
                var el = document.querySelector('{SEND_BUTTON_SELECTOR}');
                if (!el) return {{found: false}};
                if (el.offsetParent === null) return {{found: false, hidden: true}};
                if (el.disabled) return {{found: true, disabled: true}};
                var rect = el.getBoundingClientRect();
                return {{
                    found: true,
                    x: Math.round(rect.left + rect.width / 2),
                    y: Math.round(rect.top + rect.height / 2),
                    visible: true
                }};
            }})()
            """
            btn_info = await self.evaluate(js_btn)
            logger.info(f"🔘 Информация о кнопке: {btn_info}")
            
            if not btn_info or not btn_info.get('found'):
                self.step_log.append("❌ ШАГ 3: Кнопка отправки не найдена")
                return None, "Кнопка отправки не найдена", self.step_log
            
            if btn_info.get('hidden'):
                self.step_log.append("❌ ШАГ 3: Кнопка отправки скрыта")
                return None, "Кнопка отправки скрыта (возможно, нет текста)", self.step_log
            
            if btn_info.get('disabled'):
                self.step_log.append("❌ ШАГ 3: Кнопка отправки отключена")
                return None, "Кнопка отправки отключена", self.step_log
            
            # Клик по кнопке
            x, y = btn_info['x'], btn_info['y']
            await self.click_at_coords(x, y)
            await self.wait_for_load(1)
            
            # ВЕРИФИКАЦИЯ: проверяем что сообщение отправилось (поле очистилось)
            verify_send = await self.verify_send_button_clicked()
            logger.info(f"🔍 Верификация отправки: {verify_send}")
            
            if not verify_send.get('success'):
                self.step_log.append("❌ ШАГ 3: Ошибка проверки отправки")
                return None, "Ошибка проверки отправки", self.step_log
            
            if not verify_send.get('is_empty'):
                self.step_log.append(f"❌ ШАГ 3: Сообщение не отправилось! Поле не очистилось: '{verify_send.get('value')}'")
                return None, f"Сообщение не отправилось! Поле не очистилось: '{verify_send.get('value')}'", self.step_log
            
            self.step_log.append("✅ ШАГ 3: Сообщение отправлено (поле очистилось)")
            
            # ШАГ 4: Ожидание ответа
            logger.info("📌 ШАГ 4: Ожидание ответа...")
            self.step_log.append("⏳ ШАГ 4: Ожидание ответа...")
            
            max_attempts = 60
            old_response = None
            
            for attempt in range(max_attempts):
                await asyncio.sleep(1)
                
                response = await self.get_qwen_response()
                
                if response and response != old_response and len(response) > 15:
                    logger.info(f"✅ Получен ответ: {response[:50]}...")
                    self.step_log.append(f"✅ ШАГ 4: Ответ получен ({len(response)} символов)")
                    return response, None, self.step_log
                
                old_response = response
                
                if attempt % 10 == 0:
                    logger.info(f"⏳ Ожидание... {attempt}/{max_attempts}")
            
            self.step_log.append("❌ ШАГ 4: Таймаут ожидания ответа")
            return None, "Таймаут ожидания ответа", self.step_log
                
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            self.step_log.append(f"❌ Ошибка: {e}")
            return None, str(e), self.step_log

browser = BrowserHarness(CDP_URL)

# ============================================================
# КОМАНДЫ
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cookies_status = f"🍪 Куки: {len(COOKIES)} шт." if COOKIES else "🍪 Куки: НЕ ЗАГРУЖЕНЫ!"
    
    await update.message.reply_text(
        f"🤖 **Qwen Bot**\n\n"
        f"{cookies_status}\n\n"
        f"📌 /debug — состояние\n"
        f"📌 /steps — показать последние шаги",
        parse_mode='Markdown'
    )

async def steps_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать последние шаги выполнения"""
    if not browser.step_log:
        await update.message.reply_text("Нет сохраненных шагов")
        return
    
    msg = "📋 **Последние шаги:**\n\n"
    for step in browser.step_log[-15:]:
        msg += f"{step}\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        title = await browser.evaluate("document.title")
        
        textarea_value = await browser.evaluate(f"""
        (function() {{
            var el = document.querySelector('{TEXTAREA_SELECTOR}');
            return el ? el.value : null;
        }})()
        """)
        
        response = await browser.get_qwen_response()
        
        msg = f"🔍 **Отладка**\n\n"
        msg += f"Заголовок: {title}\n"
        msg += f"📝 Текст в поле: {textarea_value or 'пусто'}\n"
        msg += f"💬 Ответ Qwen: {response[:200] if response else 'нет'}\n"
        msg += f"🍪 Кук: {len(COOKIES)}\n"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = update.message.text
    
    status_msg = await update.message.reply_text("🚀 Отправляю запрос...")
    
    try:
        response, error, steps = await browser.ask_qwen(question)
        
        if error:
            # Показываем шаги при ошибке
            steps_msg = "\n\n".join(steps[-5:]) if steps else ""
            await status_msg.edit_text(f"❌ {error}\n\n{steps_msg}")
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
    app.add_handler(CommandHandler("steps", steps_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Qwen Bot запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()