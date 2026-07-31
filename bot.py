# bot.py - финальная версия с четкой последовательностью
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

# Координаты элементов из JSON-файла (rc: [x, y, width, height])
ELEMENTS = {
    # Кнопка нового чата
    'new_chat': {
        'coords': [24, 72, 20, 20],  # из JSON: sidebar-entry-fixed-list-icon
        'selector': '[aria-label="Новый чат"]'
    },
    # Поле ввода текста
    'textarea': {
        'coords': [328, 167, 245, 56],  # из JSON: message-input-textarea
        'selector': '.message-input-textarea'
    },
    # Кнопка отправки (синяя с волной)
    'send_button': {
        'coords': [720, 179, 32, 32],  # из JSON: omni-button-content-btn
        'selector': '.omni-button-content-btn'
    }
}

def get_center_coords(coords):
    """Получить центр элемента по координатам [x, y, width, height]"""
    x, y, w, h = coords
    return (x + w // 2, y + h // 2)

# ============================================================
# BROWSER HARNESS
# ============================================================

class BrowserHarness:
    def __init__(self, cdp_url="http://localhost:9222"):
        self.cdp_url = cdp_url
        self.ws_url = None
        self.current_url = None
    
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
        """Перейти на страницу"""
        logger.info(f"🌐 Переход на {url}")
        result = await self._send_cdp("Page.navigate", {"url": url})
        self.current_url = url
        return result.get("result", {})
    
    async def evaluate(self, expression):
        result = await self._send_cdp("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True
        })
        return result.get("result", {}).get("result", {}).get("value")
    
    async def wait_for_load(self, timeout=5):
        """Ожидать загрузки страницы"""
        logger.info(f"⏳ Ожидание загрузки {timeout}с...")
        await asyncio.sleep(timeout)
    
    async def click_at_coords(self, x, y, description=""):
        """Кликнуть по координатам"""
        js = f"""
        (function() {{
            var element = document.elementFromPoint({x}, {y});
            if (!element) {{
                console.log('Элемент не найден по координатам ({x}, {y})');
                return false;
            }}
            
            element.scrollIntoView({{behavior: 'smooth', block: 'center'}});
            
            // Клик
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
            logger.info(f"✅ Клик по координатам ({x}, {y}) {description}")
        else:
            logger.warning(f"❌ Не удалось кликнуть по ({x}, {y}) {description}")
        return result
    
    async def click_element_by_coords(self, element_name):
        """Кликнуть по элементу по координатам из JSON"""
        if element_name not in ELEMENTS:
            logger.error(f"❌ Элемент {element_name} не найден")
            return False
        
        element = ELEMENTS[element_name]
        coords = element['coords']
        x, y = get_center_coords(coords)
        
        return await self.click_at_coords(x, y, f"({element_name})")
    
    async def set_text_at_coords(self, element_name, text):
        """Установить текст в элемент по координатам"""
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
            element.dispatchEvent(new Event('input', {{ bubbles: true }}));
            element.dispatchEvent(new Event('change', {{ bubbles: true }}));
            element.dispatchEvent(new Event('keyup', {{ bubbles: true }}));
            return true;
        }})()
        """
        result = await self.evaluate(js)
        if result:
            logger.info(f"✅ Текст установлен в {element_name}: {text[:30]}...")
        else:
            logger.warning(f"❌ Не удалось установить текст в {element_name}")
        return result
    
    async def send_message_to_qwen(self, text):
        """Отправить сообщение в Qwen"""
        
        # ШАГ 1: Нажимаем кнопку "Новый чат"
        logger.info("📌 ШАГ 1: Создаем новый чат...")
        new_chat_clicked = await self.click_element_by_coords('new_chat')
        
        if not new_chat_clicked:
            # Пробуем через селектор
            try:
                js = """
                (function() {
                    var el = document.querySelector('[aria-label="Новый чат"]');
                    if (!el) return false;
                    el.click();
                    return true;
                })()
                """
                new_chat_clicked = await self.evaluate(js)
                if new_chat_clicked:
                    logger.info("✅ Новый чат создан через селектор")
            except:
                pass
        
        if not new_chat_clicked:
            return False, "Не удалось создать новый чат"
        
        await self.wait_for_load(2)
        
        # ШАГ 2: Вводим текст
        logger.info(f"📌 ШАГ 2: Вводим текст...")
        text_set = await self.set_text_at_coords('textarea', text)
        
        if not text_set:
            # Пробуем через селектор
            try:
                js = f"""
                (function() {{
                    var el = document.querySelector('.message-input-textarea, textarea');
                    if (!el) return false;
                    el.focus();
                    el.value = '';
                    el.value = '{text.replace("'", "\\'")}';
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    return true;
                }})()
                """
                text_set = await self.evaluate(js)
                if text_set:
                    logger.info("✅ Текст установлен через селектор")
            except:
                pass
        
        if not text_set:
            return False, "Не удалось ввести текст"
        
        await self.wait_for_load(1)
        
        # ШАГ 3: Нажимаем кнопку отправки
        logger.info("📌 ШАГ 3: Отправляем сообщение...")
        send_clicked = await self.click_element_by_coords('send_button')
        
        if not send_clicked:
            # Пробуем Enter
            logger.info("⏳ Пробуем Enter...")
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
            logger.info("⏎ Нажат Enter")
        
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
                        !text.includes('Please enter a prompt')) {
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
        """Полный цикл: переход на сайт → новый чат → текст → ответ"""
        try:
            # ШАГ 0: Переход на сайт
            logger.info("🚀 ШАГ 0: Переход на chat.qwen.ai...")
            await self.navigate("https://chat.qwen.ai/")
            await self.wait_for_load(5)
            
            # ШАГ 1-3: Отправка сообщения
            success, msg = await self.send_message_to_qwen(question)
            if not success:
                return None, msg
            
            # ШАГ 4: Ожидание ответа
            logger.info("⏳ ШАГ 4: Ожидание ответа...")
            max_attempts = 120
            
            for attempt in range(max_attempts):
                await asyncio.sleep(1)
                
                response = await self.get_last_response()
                
                if response:
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
        f"🤖 **Qwen Bot**\n\n"
        f"Работает по схеме:\n"
        f"1️⃣ Переход на сайт\n"
        f"2️⃣ Создание нового чата\n"
        f"3️⃣ Ввод текста\n"
        f"4️⃣ Отправка и получение ответа\n\n"
        f"📌 /debug — показать состояние\n"
        f"📌 /coords — показать координаты",
        parse_mode='Markdown'
    )

async def coords_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать координаты всех элементов"""
    msg = "📍 **Координаты элементов:**\n\n"
    for name, element in ELEMENTS.items():
        coords = element['coords']
        x, y, w, h = coords
        center_x, center_y = x + w//2, y + h//2
        msg += f"**{name}:**\n"
        msg += f"  Позиция: ({x}, {y})\n"
        msg += f"  Размер: {w}x{h}\n"
        msg += f"  Центр: ({center_x}, {center_y})\n\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отладка"""
    try:
        title = await browser.evaluate("document.title")
        
        # Проверяем элементы по координатам
        elements_status = {}
        for name, element in ELEMENTS.items():
            coords = element['coords']
            x, y = get_center_coords(coords)
            js = f"""
            (function() {{
                var el = document.elementFromPoint({x}, {y});
                return el ? true : false;
            }})()
            """
            exists = await browser.evaluate(js)
            elements_status[name] = exists
        
        response = await browser.get_last_response()
        
        status = "🔍 **Отладка**\n\n"
        status += f"📄 Заголовок: {title}\n\n"
        status += "**Элементы:**\n"
        for name, exists in elements_status.items():
            status += f"  {name}: {'✅' if exists else '❌'}\n"
        
        if response:
            status += f"\n📝 Последний ответ:\n{response[:200]}"
        else:
            status += "\n📝 Нет ответа"
        
        await update.message.reply_text(status, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = update.message.text
    
    status_msg = await update.message.reply_text("🚀 Начинаю работу...")
    
    try:
        # Обновляем статус
        await status_msg.edit_text("🌐 Переход на сайт...")
        
        response, error = await browser.ask_qwen(question)
        
        if error:
            await status_msg.edit_text(f"❌ {error}")
            return
        
        if not response:
            await status_msg.edit_text("❌ Не удалось получить ответ")
            return
        
        if len(response) > 4000:
            response = response[:4000] + "...\n\n(ответ обрезан)"
        
        await status_msg.edit_text(
            f"💬 **Qwen:**\n\n{response}",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("debug", debug_command))
    app.add_handler(CommandHandler("coords", coords_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Qwen Bot запущен!")
    logger.info(f"📡 CDP: {CDP_URL}")
    logger.info(f"🍪 Куки: {len(COOKIES)} шт.")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()