# bot.py - финальная версия с правильной логикой
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
# КООРДИНАТЫ ИЗ JSON И СКРИНШОТА
# ============================================================

# Координаты элементов из JSON
ELEMENTS = {
    # Кнопка нового чата (верхний левый угол)
    'new_chat': {
        'coords': [24, 72, 20, 20],
        'selector': '[aria-label="Новый чат"]'
    },
    # Поле ввода текста (внизу)
    'textarea': {
        'coords': [328, 167, 245, 56],  # из JSON
        'selector': '.message-input-textarea'
    },
    # Кнопка отправки - появляется только после ввода текста!
    'send_button': {
        'coords': [720, 179, 32, 32],  # из JSON
        'selector': '.omni-button-content-btn'
    },
    # Кнопка "Виктор" (слева от поля ввода на скриншоте)
    'victor_button': {
        'coords': [294, 185, 20, 20],  # примерные координаты
        'selector': '[aria-label="Выбрать режим"]'
    }
}

def get_center_coords(coords):
    """Получить центр элемента"""
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
    
    async def click_at_coords(self, x, y, description=""):
        """Кликнуть по координатам"""
        js = f"""
        (function() {{
            var element = document.elementFromPoint({x}, {y});
            if (!element) {{
                console.log('Элемент не найден');
                return false;
            }}
            
            element.scrollIntoView({{behavior: 'smooth', block: 'center'}});
            
            var clickEvent = new MouseEvent('click', {{
                view: window,
                bubbles: true,
                cancelable: true,
                clientX: {x},
                clientY: {y}
            }});
            element.dispatchEvent(clickEvent);
            
            return true;
        }})()
        """
        result = await self.evaluate(js)
        if result:
            logger.info(f"✅ Клик по ({x}, {y}) {description}")
        else:
            logger.warning(f"❌ Не удалось кликнуть по ({x}, {y})")
        return result
    
    async def click_element_by_coords(self, element_name):
        """Кликнуть по элементу по координатам"""
        if element_name not in ELEMENTS:
            return False
        
        element = ELEMENTS[element_name]
        coords = element['coords']
        x, y = get_center_coords(coords)
        
        return await self.click_at_coords(x, y, f"({element_name})")
    
    async def set_text_at_coords(self, element_name, text):
        """Установить текст в элемент"""
        if element_name not in ELEMENTS:
            return False
        
        element = ELEMENTS[element_name]
        coords = element['coords']
        x, y = get_center_coords(coords)
        
        js = f"""
        (function() {{
            var element = document.elementFromPoint({x}, {y});
            if (!element) return false;
            
            element.focus();
            element.click();
            element.value = '';
            element.value = '{text.replace("'", "\\'")}';
            
            // Важно: триггерим события, чтобы кнопка появилась
            element.dispatchEvent(new Event('input', {{ bubbles: true }}));
            element.dispatchEvent(new Event('change', {{ bubbles: true }}));
            element.dispatchEvent(new Event('keydown', {{ bubbles: true }}));
            element.dispatchEvent(new Event('keyup', {{ bubbles: true }}));
            
            return true;
        }})()
        """
        result = await self.evaluate(js)
        if result:
            logger.info(f"✅ Текст установлен в {element_name}")
        return result
    
    async def wait_for_send_button(self, timeout=10):
        """Ожидать появления кнопки отправки (после ввода текста)"""
        logger.info("⏳ Ожидаю появления кнопки отправки...")
        
        # Проверяем через координаты
        coords = ELEMENTS['send_button']['coords']
        x, y = get_center_coords(coords)
        
        js = f"""
        (function() {{
            var start = Date.now();
            while (Date.now() - start < {timeout * 1000}) {{
                var element = document.elementFromPoint({x}, {y});
                if (element) {{
                    var text = (element.textContent || '').trim();
                    // Проверяем, что это не пустой элемент
                    if (element.offsetParent !== null) {{
                        return true;
                    }}
                }}
                var end = Date.now() + 500;
                while (Date.now() < end) {{}}
            }}
            return false;
        }})()
        """
        return await self.evaluate(js)
    
    async def send_message_to_qwen(self, text):
        """Отправить сообщение в Qwen"""
        
        # ШАГ 1: Новый чат
        logger.info("📌 ШАГ 1: Создаем новый чат...")
        await self.click_element_by_coords('new_chat')
        await self.wait_for_load(2)
        
        # ШАГ 2: Вводим текст (это вызовет появление кнопки отправки)
        logger.info(f"📌 ШАГ 2: Вводим текст...")
        text_set = await self.set_text_at_coords('textarea', text)
        
        if not text_set:
            return False, "Не удалось ввести текст"
        
        # Ждем появления кнопки отправки
        await self.wait_for_load(1)
        
        # ШАГ 3: Ожидаем появления кнопки отправки
        logger.info("📌 ШАГ 3: Ожидаем появления кнопки отправки...")
        send_btn_visible = await self.wait_for_send_button(timeout=10)
        
        if send_btn_visible:
            logger.info("✅ Кнопка отправки появилась!")
            await self.click_element_by_coords('send_button')
        else:
            logger.info("⏳ Кнопка не появилась, пробуем Enter...")
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
        return True, "Сообщение отправлено"
    
    async def get_last_response(self):
        """Получить последний ответ от Qwen"""
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
        """Полный цикл работы"""
        try:
            # Переход на сайт
            logger.info("🚀 Переход на chat.qwen.ai...")
            await self.navigate("https://chat.qwen.ai/")
            await self.wait_for_load(5)
            
            # Отправка сообщения
            success, msg = await self.send_message_to_qwen(question)
            if not success:
                return None, msg
            
            # Ожидание ответа
            logger.info("⏳ Ожидание ответа...")
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
        f"🤖 **Qwen Bot**\n\n"
        f"Как работает:\n"
        f"1️⃣ Переход на сайт\n"
        f"2️⃣ Новый чат\n"
        f"3️⃣ Ввод текста (появляется кнопка отправки)\n"
        f"4️⃣ Отправка\n"
        f"5️⃣ Получение ответа\n\n"
        f"📌 /debug — состояние\n"
        f"📌 /coords — координаты",
        parse_mode='Markdown'
    )

async def coords_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "📍 **Координаты элементов:**\n\n"
    for name, element in ELEMENTS.items():
        coords = element['coords']
        x, y, w, h = coords
        center_x, center_y = x + w//2, y + h//2
        msg += f"**{name}:** ({center_x}, {center_y})\n"
        msg += f"  Позиция: ({x}, {y}) Размер: {w}x{h}\n\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        title = await browser.evaluate("document.title")
        
        # Проверяем элементы
        status = {}
        for name, element in ELEMENTS.items():
            coords = element['coords']
            x, y = get_center_coords(coords)
            js = f"!!document.elementFromPoint({x}, {y})"
            exists = await browser.evaluate(js)
            status[name] = exists
        
        response = await browser.get_last_response()
        
        msg = "🔍 **Отладка**\n\n"
        msg += f"📄 {title}\n\n"
        msg += "**Элементы:**\n"
        for name, exists in status.items():
            msg += f"  {name}: {'✅' if exists else '❌'}\n"
        
        if response:
            msg += f"\n📝 Ответ: {response[:150]}..."
        
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = update.message.text
    
    status_msg = await update.message.reply_text("🚀 Запускаю...")
    
    try:
        await status_msg.edit_text("🌐 Переход на сайт...")
        
        response, error = await browser.ask_qwen(question)
        
        if error:
            await status_msg.edit_text(f"❌ {error}")
            return
        
        if not response:
            await status_msg.edit_text("❌ Нет ответа")
            return
        
        if len(response) > 4000:
            response = response[:4000] + "..."
        
        await status_msg.edit_text(
            f"💬 **Qwen:**\n\n{response}",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ {str(e)[:200]}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("debug", debug_command))
    app.add_handler(CommandHandler("coords", coords_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Qwen Bot запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()