# bot.py - исправленная версия с правильной отправкой
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
        result = await self._send_cdp("Page.navigate", {"url": url})
        return result.get("result", {})
    
    async def evaluate(self, expression):
        result = await self._send_cdp("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True
        })
        return result.get("result", {}).get("result", {}).get("value")
    
    async def wait_for_load(self, timeout=15):
        await asyncio.sleep(timeout)
    
    async def click_element(self, selector):
        js = f"""
        (function() {{
            var el = document.querySelector('{selector}');
            if (!el) return false;
            el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
            el.click();
            el.dispatchEvent(new MouseEvent('click', {{ bubbles: true }}));
            return true;
        }})()
        """
        return await self.evaluate(js)
    
    async def set_text(self, selector, text):
        js = f"""
        (function() {{
            var el = document.querySelector('{selector}');
            if (!el) return false;
            el.focus();
            el.value = '';
            el.value = '{text.replace("'", "\\'")}';
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            el.dispatchEvent(new Event('keyup', {{ bubbles: true }}));
            return true;
        }})()
        """
        return await self.evaluate(js)
    
    async def create_new_chat(self):
        """Создать новый чат"""
        # Нажимаем кнопку "Новый чат"
        new_chat_selectors = [
            '[aria-label="Новый чат"]',
            '.sidebar-entry-fixed-list-content[role="button"]',
            '.sidebar-entry-fixed-list-content'
        ]
        
        for selector in new_chat_selectors:
            try:
                result = await self.click_element(selector)
                if result:
                    logger.info(f"✅ Создан новый чат через: {selector}")
                    await self.wait_for_load(2)
                    return True
            except Exception as e:
                logger.warning(f"Не удалось нажать {selector}: {e}")
        
        return False
    
    async def get_last_response(self):
        """Получить последний ответ от Qwen"""
        js = """
        (function() {
            // Ищем все сообщения
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
                    // Исключаем системные сообщения
                    if (text && 
                        text.length > 10 && 
                        !text.includes('AutoChoose') && 
                        !text.includes('Get Started') &&
                        !text.includes('style to create') &&
                        !text.includes('window.iconfontsvgstring') &&
                        !text.includes('Please enter a prompt')) {
                        allMessages.push({
                            text: text,
                            index: i,
                            time: Date.now()
                        });
                    }
                }
            }
            
            if (allMessages.length > 0) {
                // Сортируем по времени (последние сверху)
                allMessages.sort(function(a, b) { 
                    return b.time - a.time || b.index - a.index; 
                });
                return allMessages[0].text;
            }
            return null;
        })()
        """
        return await self.evaluate(js)
    
    async def send_message_to_qwen(self, text):
        """Отправить сообщение в Qwen"""
        
        # 1. Создаем новый чат
        await self.create_new_chat()
        
        # 2. Находим текстовое поле
        textarea_selectors = [
            '.message-input-textarea',
            'textarea[placeholder*="помочь"]',
            'textarea',
            '[contenteditable="true"]'
        ]
        
        text_set = False
        for selector in textarea_selectors:
            try:
                result = await self.set_text(selector, text)
                if result:
                    text_set = True
                    logger.info(f"✅ Текст установлен в: {selector}")
                    break
            except Exception as e:
                logger.warning(f"Не удалось установить текст в {selector}: {e}")
        
        if not text_set:
            return False, "Не найдено поле ввода"
        
        await asyncio.sleep(1)
        
        # 3. Ищем и нажимаем кнопку отправки (из JSON)
        send_selectors = [
            '.omni-button-content-btn',  # основная кнопка из JSON
            'button[aria-label*="Голосовой режим"]',
            '.omni-button-content',
            '[role="button"]',
            'button'
        ]
        
        clicked = False
        for selector in send_selectors:
            try:
                # Проверяем, есть ли элемент
                has_element = await self.evaluate(f"!!document.querySelector('{selector}')")
                if has_element:
                    result = await self.click_element(selector)
                    if result:
                        clicked = True
                        logger.info(f"✅ Кнопка нажата: {selector}")
                        break
            except Exception as e:
                logger.warning(f"Не удалось нажать {selector}: {e}")
        
        if not clicked:
            # Пробуем Enter
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
        
        await asyncio.sleep(1)
        return True, "Сообщение отправлено"
    
    async def ask_qwen(self, question):
        """Задать вопрос Qwen"""
        try:
            logger.info(f"🌐 Открываю Qwen...")
            await self.navigate("https://chat.qwen.ai/")
            await self.wait_for_load(5)
            
            logger.info(f"✏️ Отправляю вопрос: {question[:50]}...")
            success, msg = await self.send_message_to_qwen(question)
            
            if not success:
                return None, msg
            
            logger.info("⏳ Ожидаю ответ...")
            
            # Ждем ответ с проверкой каждую секунду
            max_attempts = 120
            
            for attempt in range(max_attempts):
                await asyncio.sleep(1)
                
                # Получаем текущий ответ
                response = await self.get_last_response()
                
                if response:
                    logger.info(f"📝 Найден ответ: {response[:50]}...")
                    return response, None
                
                if attempt % 10 == 0:
                    logger.info(f"⏳ Ожидание... {attempt}/{max_attempts}")
            
            # Проверяем, не появилось ли сообщение об ошибке
            error_msg = await self.evaluate("""
            (function() {
                var els = document.querySelectorAll('[class*="error"], [class*="warning"]');
                for (var i = 0; i < els.length; i++) {
                    var text = (els[i].textContent || '').trim();
                    if (text) return text;
                }
                return null;
            })()
            """)
            
            if error_msg:
                return None, f"Ошибка: {error_msg}"
            
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
        f"Просто отправьте мне сообщение!\n"
        f"Я создам новый чат в Qwen и передам ваш вопрос.\n\n"
        f"📌 /clear — перезагрузить страницу\n"
        f"📌 /debug — показать состояние",
        parse_mode='Markdown'
    )

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await browser.navigate("https://chat.qwen.ai/")
        await browser.wait_for_load(3)
        await update.message.reply_text("✅ Страница перезагружена")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отладка - показать текущее состояние страницы"""
    try:
        # Получаем заголовок
        title = await browser.evaluate("document.title")
        
        # Проверяем наличие полей
        has_textarea = await browser.evaluate(
            "!!document.querySelector('.message-input-textarea, textarea')"
        )
        
        # Ищем все кнопки
        buttons = await browser.evaluate("""
        (function() {
            var btns = [];
            var els = document.querySelectorAll('button, [role="button"]');
            for (var i = 0; i < els.length; i++) {
                var text = (els[i].textContent || '').trim();
                var aria = els[i].getAttribute('aria-label') || '';
                if (text || aria) {
                    btns.push(text || aria);
                }
            }
            return btns.join(' | ');
        })()
        """)
        
        # Получаем последний ответ
        response = await browser.get_last_response()
        
        # Получаем все сообщения
        messages = await browser.evaluate("""
        (function() {
            var texts = [];
            var els = document.querySelectorAll('.message-content, .chat-message');
            for (var i = 0; i < els.length; i++) {
                var text = (els[i].textContent || '').trim();
                if (text && text.length > 5 && text.length < 500) {
                    texts.push(text);
                }
            }
            return texts.join(' | ');
        })()
        """)
        
        await update.message.reply_text(
            f"🔍 **Отладка**\n\n"
            f"📄 Заголовок: {title}\n"
            f"✏️ Поле ввода: {'✅' if has_textarea else '❌'}\n"
            f"🔘 Кнопки: {buttons[:200] if buttons else 'Нет кнопок'}\n"
            f"💬 Сообщения на странице:\n{messages[:300] if messages else 'Нет сообщений'}\n\n"
            f"📝 Последний ответ:\n{response[:200] if response else 'Нет ответа'}",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = update.message.text
    
    status_msg = await update.message.reply_text("💭 Создаю новый чат и отправляю вопрос Qwen...")
    
    try:
        response, error = await browser.ask_qwen(question)
        
        if error:
            await status_msg.edit_text(f"❌ {error}")
            return
        
        if not response:
            await status_msg.edit_text("❌ Не удалось получить ответ от Qwen")
            return
        
        # Обрезаем длинный ответ
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
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("debug", debug_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Qwen Bot запущен!")
    logger.info(f"📡 CDP: {CDP_URL}")
    logger.info(f"🍪 Куки: {len(COOKIES)} шт.")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()