# bot.py - ФИНАЛЬНАЯ ВЕРСИЯ С ТОЧНЫМ СЕЛЕКТОРОМ
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

# Кнопка отправки
SEND_BUTTON_SELECTOR = ".message-input-right-button-send"

# ОТВЕТ QWEN - ТОЧНЫЙ СЕЛЕКТОР!
RESPONSE_SELECTOR = "div.custom-qwen-markdown > div.md-text-select > div.md-text-select__content > div.qwen-markdown.qwen-markdown-loose > div.qwen-markdown-paragraph"

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
    
    async def click_element(self, selector):
        """Найти и кликнуть по элементу"""
        js = f"""
        (function() {{
            var el = document.querySelector('{selector}');
            if (!el) return {{found: false, error: 'Элемент не найден'}};
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
        """Установить текст в поле"""
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
        """Получить значение текстового поля"""
        js = f"""
        (function() {{
            var el = document.querySelector('{selector}');
            return el ? el.value : null;
        }})()
        """
        return await self.evaluate(js)
    
    async def verify_text_set(self, selector, expected_text):
        """Проверить, установился ли текст"""
        actual = await self.get_text_value(selector)
        return {
            'success': True,
            'value': actual,
            'matches': actual == expected_text
        }
    
    async def verify_send(self):
        """Проверить, отправилось ли сообщение (поле пустое)"""
        value = await self.get_text_value(TEXTAREA_SELECTOR)
        return {
            'success': True,
            'is_empty': value == '' or value is None,
            'value': value
        }
    
    async def get_qwen_response(self):
        """Получить ответ Qwen по точному селектору"""
        js = f"""
        (function() {{
            var el = document.querySelector('{RESPONSE_SELECTOR}');
            if (!el) return null;
            
            var text = (el.textContent || '').trim();
            if (!text || text.length < 3) return null;
            
            // Проверяем что это не системное сообщение
            var systemPatterns = [
                'AutoChoose', 'Get Started', 'Please enter',
                'Что бы вы хотели', 'Log in', 'Sign up',
                'Скачать приложение', 'Войти', 'Завершено размышление',
                'Thinking completed', 'Выберите', 'Ваш выбор',
                'Qwen3.7-Plus', 'Новый чат', 'Сообщество', 'Coder',
                'Проекты', 'Все чаты', 'Используя Qwen Studio',
                'Пользовательские условия', 'Политика конфиденциальности'
            ];
            
            for (var p of systemPatterns) {{
                if (text.includes(p)) {{
                    return null;
                }}
            }}
            
            return text;
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
            
            result = await self.set_text(TEXTAREA_SELECTOR, question)
            logger.info(f"📝 Результат ввода: {result}")
            
            if not result or not result.get('success'):
                return None, "Не удалось ввести текст", self.step_log
            
            # Проверяем что текст установился
            verify = await self.verify_text_set(TEXTAREA_SELECTOR, question)
            
            if not verify.get('matches'):
                self.step_log.append(f"❌ ШАГ 2: Текст не установился. Ожидалось: '{question}', Получено: '{verify.get('value')}'")
                return None, f"Текст не установился", self.step_log
            
            self.step_log.append(f"✅ ШАГ 2: Текст установлен: '{verify.get('value')}'")
            await self.wait_for_load(0.5)
            
            # ШАГ 3: Отправка
            logger.info("📌 ШАГ 3: Отправка...")
            
            # Пробуем нажать кнопку
            clicked = await self.click_element(SEND_BUTTON_SELECTOR)
            
            if not clicked:
                logger.info("⌨️ Кнопка не нажалась, пробую Enter...")
                await self.send_enter()
            
            await self.wait_for_load(1)
            
            # Проверяем что сообщение отправилось (поле очистилось)
            verify_send = await self.verify_send()
            
            if not verify_send.get('is_empty'):
                self.step_log.append(f"❌ ШАГ 3: Сообщение не отправилось! Поле: '{verify_send.get('value')}'")
                return None, f"Сообщение не отправилось", self.step_log
            
            self.step_log.append("✅ ШАГ 3: Сообщение отправлено (поле очистилось)")
            
            # ШАГ 4: Ожидание ответа
            logger.info("📌 ШАГ 4: Ожидание ответа...")
            self.step_log.append("⏳ ШАГ 4: Ожидание ответа...")
            
            max_attempts = 60
            
            for attempt in range(max_attempts):
                await asyncio.sleep(1)
                
                response = await self.get_qwen_response()
                
                if response and len(response) > 5:
                    logger.info(f"✅ Получен ответ: {response[:50]}...")
                    self.step_log.append(f"✅ ШАГ 4: Ответ получен ({len(response)} символов)")
                    return response, None, self.step_log
                
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
        f"📌 /steps — показать шаги",
        parse_mode='Markdown'
    )

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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Qwen Bot запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()