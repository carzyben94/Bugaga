# bot.py - с проверкой появления нового сообщения
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
    
    async def click_element(self, selector):
        js = f"""
        (function() {{
            var el = document.querySelector('{selector}');
            if (!el) return {{found: false}};
            if (el.offsetParent === null) return {{found: false, hidden: true}};
            if (el.disabled) return {{found: true, disabled: true}};
            var rect = el.getBoundingClientRect();
            return {{
                found: true,
                x: Math.round(rect.left + rect.width / 2),
                y: Math.round(rect.top + rect.height / 2)
            }};
        }})()
        """
        result = await self.evaluate(js)
        
        if result and result.get('found') and not result.get('disabled'):
            x, y = result['x'], result['y']
            return await self.click_at_coords(x, y)
        return False
    
    async def set_text(self, selector, text):
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
    
    async def get_text_value(self, selector):
        js = f"""
        (function() {{
            var el = document.querySelector('{selector}');
            return el ? el.value : null;
        }})()
        """
        return await self.evaluate(js)
    
    async def get_all_elements_with_text(self):
        """Получить все элементы с текстом"""
        js = """
        (function() {
            var results = [];
            var allElements = document.querySelectorAll('div, span, p, h1, h2, h3, h4, h5, h6, li, td, th, label, button, a');
            
            for (var i = 0; i < allElements.length; i++) {
                var el = allElements[i];
                if (el.offsetParent === null) continue;
                
                var text = (el.textContent || '').trim();
                if (!text || text.length < 3) continue;
                
                // Пропускаем скрытые
                var style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') continue;
                
                // Пропускаем системные
                var systemPatterns = [
                    'AutoChoose', 'Get Started', 'Please enter',
                    'Что бы вы хотели', 'Log in', 'Sign up',
                    'Скачать приложение', 'Войти', 'Завершено размышление',
                    'Thinking completed', 'Выберите', 'Ваш выбор',
                    'Qwen3.7-Plus', 'Новый чат', 'Сообщество', 'Coder',
                    'Проекты', 'Все чаты', 'Используя Qwen Studio',
                    'Пользовательские условия', 'Политика конфиденциальности'
                ];
                
                var isSystem = false;
                for (var p of systemPatterns) {
                    if (text.includes(p)) {
                        isSystem = true;
                        break;
                    }
                }
                if (isSystem) continue;
                
                // Строим короткий селектор
                var selector = '';
                if (el.id) {
                    selector = '#' + el.id;
                } else if (el.className && typeof el.className === 'string') {
                    var classes = el.className.split(' ').filter(c => c && c.length > 0);
                    if (classes.length > 0) {
                        selector = '.' + classes.join('.');
                    }
                }
                if (!selector) {
                    selector = el.tagName.toLowerCase();
                }
                
                results.push({
                    text: text.slice(0, 150),
                    length: text.length,
                    selector: selector,
                    tag: el.tagName,
                    class: el.className || '',
                    id: el.id || ''
                });
            }
            
            // Сортируем по длине
            results.sort(function(a, b) { return b.length - a.length; });
            return results;
        })()
        """
        return await self.evaluate(js)
    
    async def get_qwen_response(self):
        """Найти ответ Qwen среди всех элементов"""
        all_elements = await self.get_all_elements_with_text()
        
        # Ищем самый длинный текст (обычно это ответ)
        for el in all_elements:
            if el['length'] > 20:
                # Проверяем что это не вопрос пользователя
                if 'message-input' not in el['selector'] and 'textarea' not in el['selector']:
                    return el['text']
        
        return None
    
    async def send_enter(self):
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
        self.step_log = []
        
        try:
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
            
            # Запоминаем элементы до отправки
            before_texts = await self.get_all_elements_with_text()
            self.step_log.append(f"📝 Текстов до отправки: {len(before_texts)}")
            
            logger.info(f"📌 ШАГ 2: Ввод текста: {question[:30]}...")
            result = await self.set_text(TEXTAREA_SELECTOR, question)
            
            if not result or not result.get('success'):
                return None, "Не удалось ввести текст", self.step_log
            
            verify = await self.get_text_value(TEXTAREA_SELECTOR)
            if verify != question:
                self.step_log.append(f"❌ ШАГ 2: Текст не установился. Получено: '{verify}'")
                return None, f"Текст не установился", self.step_log
            
            self.step_log.append(f"✅ ШАГ 2: Текст установлен: '{verify}'")
            await self.wait_for_load(0.5)
            
            logger.info("📌 ШАГ 3: Отправка...")
            
            # Пробуем найти и нажать кнопку
            clicked = await self.click_element(SEND_BUTTON_SELECTOR)
            
            if not clicked:
                logger.info("⌨️ Кнопка не нажалась, пробую Enter...")
                await self.send_enter()
            
            await self.wait_for_load(2)
            
            # Проверяем поле
            field_value = await self.get_text_value(TEXTAREA_SELECTOR)
            self.step_log.append(f"📝 Поле после отправки: '{field_value}'")
            
            if field_value and field_value != '':
                self.step_log.append(f"❌ ШАГ 3: Поле не очистилось! Значение: '{field_value}'")
                return None, f"Поле не очистилось", self.step_log
            
            self.step_log.append("✅ ШАГ 3: Поле очистилось (сообщение отправлено)")
            
            # Ждем появления нового текста
            logger.info("📌 ШАГ 4: Ожидание ответа...")
            self.step_log.append("⏳ ШАГ 4: Ожидание ответа...")
            
            max_attempts = 60
            
            for attempt in range(max_attempts):
                await asyncio.sleep(1)
                
                # Проверяем новые элементы
                after_texts = await self.get_all_elements_with_text()
                
                # Ищем новые тексты
                before_set = set([t['text'] for t in before_texts])
                new_texts = []
                
                for t in after_texts:
                    if t['text'] not in before_set and t['length'] > 10:
                        new_texts.append(t)
                
                if new_texts:
                    # Сортируем по длине и берем самый длинный
                    new_texts.sort(key=lambda x: x['length'], reverse=True)
                    response = new_texts[0]['text']
                    
                    # Проверяем что это не наш вопрос
                    if question not in response and len(response) > 10:
                        logger.info(f"✅ Найден новый текст: {response[:50]}...")
                        self.step_log.append(f"✅ ШАГ 4: Ответ найден ({len(response)} символов)")
                        return response, None, self.step_log
                
                if attempt % 10 == 0:
                    logger.info(f"⏳ Ожидание... {attempt}/{max_attempts}")
                    self.step_log.append(f"⏳ Попытка {attempt}: новых текстов {len(new_texts) if new_texts else 0}")
            
            self.step_log.append("❌ ШАГ 4: Таймаут")
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
        f"📌 /steps — показать шаги\n"
        f"📌 /texts — показать все тексты",
        parse_mode='Markdown'
    )

async def texts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать все тексты на странице"""
    try:
        all_texts = await browser.get_all_elements_with_text()
        
        if not all_texts:
            await update.message.reply_text("Нет текстов на странице")
            return
        
        msg = f"📄 **Все тексты на странице ({len(all_texts)}):**\n\n"
        for i, t in enumerate(all_texts[:15]):
            msg += f"{i+1}. [{t['tag']}] {t['text'][:100]}...\n"
            msg += f"   Селектор: {t['selector']}\n\n"
        
        if len(all_texts) > 15:
            msg += f"... и еще {len(all_texts) - 15} текстов"
        
        await update.message.reply_text(msg[:4000], parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def steps_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        textarea_value = await browser.get_text_value(TEXTAREA_SELECTOR)
        
        all_texts = await browser.get_all_elements_with_text()
        response = None
        for t in all_texts:
            if t['length'] > 20 and 'message-input' not in t['selector']:
                response = t['text']
                break
        
        msg = f"🔍 **Отладка**\n\n"
        msg += f"Заголовок: {title}\n"
        msg += f"📝 Текст в поле: {textarea_value or 'пусто'}\n"
        msg += f"📄 Всего текстов: {len(all_texts)}\n"
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
            steps_msg = "\n".join(steps[-5:]) if steps else ""
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
    app.add_handler(CommandHandler("texts", texts_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Qwen Bot запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()