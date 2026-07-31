# bot.py - с автоматическим A11Y парсингом
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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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

TEXTAREA_SELECTOR = ".message-input-textarea"
SEND_BUTTON_SELECTOR = ".omni-button-content-btn"

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
    
    async def wait_for_load(self, timeout=3):
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
    
    async def parse_a11y_tree(self):
        """Парсинг Accessibility Tree на лету"""
        js = """
        (function() {
            var results = [];
            var allElements = document.querySelectorAll('[role], div, span, p, h1, h2, h3, h4, h5, h6, li, td, th, label, button, a');
            
            for (var i = 0; i < allElements.length; i++) {
                var el = allElements[i];
                if (el.offsetParent === null) continue;
                
                var text = (el.textContent || '').trim();
                if (!text || text.length < 3) continue;
                
                var role = el.getAttribute('role') || el.tagName.toLowerCase();
                var ariaLabel = el.getAttribute('aria-label') || '';
                var className = el.className || '';
                var id = el.id || '';
                
                // Проверяем что это не системное сообщение
                var systemPatterns = [
                    'AutoChoose', 'Get Started', 'Please enter',
                    'Что бы вы хотели', 'Log in', 'Sign up',
                    'Скачать приложение', 'Войти', 'Завершено размышление',
                    'Thinking completed', 'Выберите', 'Ваш выбор',
                    'Qwen3.7-Plus', 'Новый чат', 'Сообщество', 'Coder',
                    'Проекты', 'Все чаты', 'Используя Qwen Studio',
                    'Пользовательские условия', 'Политика конфиденциальности',
                    'Сообщить', 'Первое изображение', 'Выберите один из образцов'
                ];
                
                var isSystem = false;
                for (var p of systemPatterns) {
                    if (text.includes(p)) {
                        isSystem = true;
                        break;
                    }
                }
                
                // Также проверяем по aria-label
                for (var p of systemPatterns) {
                    if (ariaLabel.includes(p)) {
                        isSystem = true;
                        break;
                    }
                }
                
                if (!isSystem) {
                    // Определяем тип элемента
                    var elementType = 'text';
                    if (role === 'button' || el.tagName === 'BUTTON') elementType = 'button';
                    else if (role === 'input' || el.tagName === 'INPUT') elementType = 'input';
                    else if (role === 'textarea' || el.tagName === 'TEXTAREA') elementType = 'textarea';
                    else if (role === 'img' || el.tagName === 'IMG') elementType = 'image';
                    else if (role === 'link' || el.tagName === 'A') elementType = 'link';
                    
                    // Собираем селектор
                    var selector = '';
                    if (id) {
                        selector = '#' + id;
                    } else if (className && typeof className === 'string') {
                        var classes = className.split(' ').filter(c => c && c.length > 0);
                        if (classes.length > 0) {
                            selector = '.' + classes.join('.');
                        }
                    }
                    
                    results.push({
                        text: text.slice(0, 300),
                        length: text.length,
                        role: role,
                        elementType: elementType,
                        selector: selector || el.tagName.toLowerCase(),
                        ariaLabel: ariaLabel.slice(0, 100),
                        className: className.slice(0, 100),
                        id: id
                    });
                }
            }
            
            // Убираем дубликаты по тексту
            var unique = [];
            var seen = new Set();
            for (var i = 0; i < results.length; i++) {
                var key = results[i].text.slice(0, 50) + results[i].role;
                if (!seen.has(key)) {
                    seen.add(key);
                    unique.push(results[i]);
                }
            }
            
            // Сортируем по длине текста (самые длинные сверху)
            unique.sort(function(a, b) { return b.length - a.length; });
            return unique;
        })()
        """
        return await self.evaluate(js)
    
    async def find_response_in_a11y(self, question):
        """Найти ответ в Accessibility Tree"""
        logger.info("🔍 Анализирую Accessibility Tree...")
        
        # Получаем все элементы из A11Y
        elements = await self.parse_a11y_tree()
        logger.info(f"📝 Найдено элементов в A11Y: {len(elements)}")
        
        # Ищем ответ (самый длинный текст, который не является вопросом)
        for el in elements:
            # Проверяем что это не кнопка, не поле ввода, не ссылка
            if el['elementType'] in ['button', 'input', 'textarea', 'link', 'image']:
                continue
            
            # Проверяем что это не наш вопрос
            if question in el['text']:
                continue
            
            # Проверяем что текст достаточно длинный (это обычно ответ)
            if el['length'] > 20:
                logger.info(f"✅ Найден ответ: {el['text'][:50]}...")
                logger.info(f"   Роль: {el['role']}, Селектор: {el['selector']}")
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
        """Задать вопрос и найти ответ через A11Y"""
        try:
            # ШАГ 1: Переход на сайт
            logger.info("🚀 Переход на chat.qwen.ai...")
            await self.navigate("https://chat.qwen.ai/")
            await self.wait_for_load(5)
            
            # ШАГ 2: Установка кук
            if COOKIES:
                await self.set_cookies(COOKIES)
                await self.wait_for_load(2)
                await self.navigate("https://chat.qwen.ai/")
                await self.wait_for_load(5)
            
            # ШАГ 3: Ввод текста
            logger.info(f"📌 Ввод текста: {question[:30]}...")
            result = await self.set_text(TEXTAREA_SELECTOR, question)
            
            if not result or not result.get('success'):
                return None, "Не удалось ввести текст"
            
            await self.wait_for_load(0.5)
            
            # ШАГ 4: Отправка
            logger.info("📤 Отправка сообщения...")
            
            # Пробуем кнопку отправки
            clicked = await self.click_element(SEND_BUTTON_SELECTOR)
            
            if not clicked:
                logger.info("⌨️ Кнопка не нажалась, пробую Enter...")
                await self.send_enter()
            
            await self.wait_for_load(2)
            
            # ШАГ 5: Поиск ответа через A11Y
            logger.info("⏳ Ожидание ответа...")
            max_attempts = 60
            
            for attempt in range(max_attempts):
                await asyncio.sleep(1)
                
                response = await self.find_response_in_a11y(question)
                
                if response:
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
        f"🤖 **Qwen Bot (A11Y)**\n\n"
        f"{cookies_status}\n\n"
        f"Бот автоматически парсит Accessibility Tree\n"
        f"для поиска ответа!\n\n"
        f"📌 /debug — состояние\n"
        f"📌 /a11y — показать A11Y дерево",
        parse_mode='Markdown'
    )

async def a11y_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать Accessibility Tree"""
    try:
        elements = await browser.parse_a11y_tree()
        
        if not elements:
            await update.message.reply_text("Нет элементов в A11Y дереве")
            return
        
        msg = f"🌳 **Accessibility Tree ({len(elements)} элементов)**\n\n"
        
        for i, el in enumerate(elements[:15]):
            msg += f"{i+1}. [{el['elementType']}] {el['text'][:80]}...\n"
            msg += f"   Роль: {el['role']}\n"
            msg += f"   Длина: {el['length']}\n\n"
        
        if len(elements) > 15:
            msg += f"... и еще {len(elements) - 15} элементов"
        
        await update.message.reply_text(msg[:4000], parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        title = await browser.evaluate("document.title")
        textarea_value = await browser.get_text_value(TEXTAREA_SELECTOR)
        
        # Получаем A11Y
        elements = await browser.parse_a11y_tree()
        
        response = None
        for el in elements:
            if el['length'] > 20 and el['elementType'] == 'text':
                response = el['text']
                break
        
        msg = f"🔍 **Отладка**\n\n"
        msg += f"Заголовок: {title}\n"
        msg += f"📝 Текст в поле: {textarea_value or 'пусто'}\n"
        msg += f"🌳 A11Y элементов: {len(elements)}\n"
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
    app.add_handler(CommandHandler("a11y", a11y_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Qwen Bot запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()