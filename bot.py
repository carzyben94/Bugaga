# bot.py - исправленная версия с правильным поиском ответов
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
    
    async def get_element_text(self, selector):
        js = f"""
        (function() {{
            var el = document.querySelector('{selector}');
            if (!el) return null;
            return (el.textContent || '').trim();
        }})()
        """
        return await self.evaluate(js)
    
    async def send_message_to_qwen(self, text):
        """Отправить сообщение в Qwen"""
        
        # 1. Ждем загрузки
        await self.wait_for_load(2)
        
        # 2. Нажимаем кнопку "Новый чат" если есть
        try:
            await self.click_element('[aria-label="Новый чат"]')
            await self.wait_for_load(1)
        except:
            pass
        
        # 3. Находим текстовое поле
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
        
        # 4. Ищем кнопку отправки
        send_selectors = [
            '.omni-button-content-btn',
            'button[aria-label*="Голосовой режим"]',
            '.omni-button-content',
            '[role="button"] svg[type="icon-line-waveform"]'
        ]
        
        clicked = False
        for selector in send_selectors:
            try:
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
        
        return True, "Сообщение отправлено"
    
    async def wait_for_response(self, timeout=120):
        """Ожидать ответ от Qwen"""
        
        # JavaScript для поиска ответа с правильными селекторами
        js = f"""
        (function() {{
            var startTime = Date.now();
            var maxWait = {timeout * 1000};
            var lastResponse = null;
            var stableCount = 0;
            
            function findResponse() {{
                // Правильные селекторы для Qwen из JSON
                var selectors = [
                    '.message-content',           // из JSON
                    '.chat-message',              // из JSON
                    '[class*="message"]:not(:empty)',
                    '.ant-message',
                    '[class*="response"]'
                ];
                
                var allTexts = [];
                for (var s of selectors) {{
                    var els = document.querySelectorAll(s);
                    for (var i = 0; i < els.length; i++) {{
                        var text = (els[i].textContent || '').trim();
                        // Фильтруем системные сообщения
                        if (text && 
                            text.length > 10 && 
                            !text.includes('AutoChoose') && 
                            !text.includes('Get Started') &&
                            !text.includes('style to create') &&
                            !text.includes('window.iconfontsvgstring')) {{
                            allTexts.push(text);
                        }}
                    }}
                }}
                
                if (allTexts.length > 0) {{
                    // Сортируем по длине (самый длинный текст - скорее всего ответ)
                    allTexts.sort(function(a, b) {{ return b.length - a.length; }});
                    return allTexts[0];
                }}
                return null;
            }}
            
            while (Date.now() - startTime < maxWait) {{
                var response = findResponse();
                
                if (response) {{
                    if (response === lastResponse) {{
                        stableCount++;
                    }} else {{
                        lastResponse = response;
                        stableCount = 0;
                    }}
                    
                    // Если ответ стабилен и достаточно длинный
                    if (stableCount > 5 && response.length > 20) {{
                        return response;
                    }}
                }}
                
                // Проверяем индикатор загрузки
                var loading = document.querySelector(
                    '[class*="loading"], [class*="typing"], .anticon-loading, [class*="thinking"]'
                );
                
                if (!loading && response && response.length > 30) {{
                    return response;
                }}
                
                // Ждем 1 секунду
                var end = Date.now() + 1000;
                while (Date.now() < end) {{}}
            }}
            
            return lastResponse || null;
        }})()
        """
        
        result = await self.evaluate(js)
        return result
    
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
            response = await self.wait_for_response(120)
            
            if response:
                logger.info(f"✅ Получен ответ: {response[:100]}...")
                return response, None
            else:
                # Пробуем получить все тексты для отладки
                all_texts = await self.evaluate("""
                (function() {
                    var texts = [];
                    var els = document.querySelectorAll('[class*="message"]');
                    for (var i = 0; i < els.length; i++) {
                        var text = (els[i].textContent || '').trim();
                        if (text && text.length > 5) {
                            texts.push(text);
                        }
                    }
                    return texts.join(' | ');
                })()
                """)
                logger.error(f"❌ Найдены тексты: {all_texts}")
                return None, "Не удалось получить ответ от Qwen"
                
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
        f"Я передам его Qwen через веб-интерфейс.\n\n"
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
        
        has_send_btn = await browser.evaluate(
            "!!document.querySelector('.omni-button-content-btn')"
        )
        
        # Получаем все сообщения
        messages = await browser.evaluate("""
        (function() {
            var texts = [];
            var els = document.querySelectorAll('.message-content, .chat-message, [class*="message"]');
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
            f"📤 Кнопка отправки: {'✅' if has_send_btn else '❌'}\n"
            f"💬 Сообщения на странице:\n{messages[:500] if messages else 'Нет сообщений'}",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = update.message.text
    
    status_msg = await update.message.reply_text("💭 Обращаюсь к Qwen...")
    
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