# bot.py - улучшенная версия с правильными селекторами из JSON
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
        """Кликнуть по элементу"""
        js = f"""
        (function() {{
            var el = document.querySelector('{selector}');
            if (!el) return false;
            el.click();
            el.dispatchEvent(new MouseEvent('click', {{ bubbles: true }}));
            return true;
        }})()
        """
        return await self.evaluate(js)
    
    async def set_text(self, selector, text):
        """Установить текст"""
        js = f"""
        (function() {{
            var el = document.querySelector('{selector}');
            if (!el) return false;
            el.value = '{text.replace("'", "\\'")}';
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return true;
        }})()
        """
        return await self.evaluate(js)
    
    async def send_message_to_qwen(self, text):
        """Отправить сообщение в Qwen используя правильные селекторы из JSON"""
        
        # 1. Находим текстовое поле (из JSON: t="textarea", cl="message-input-textarea")
        textarea_selectors = [
            '.message-input-textarea',  # основной класс из JSON
            'textarea[placeholder*="помочь"]',
            'textarea[placeholder*="help"]',
            '.chat-message-input textarea'
        ]
        
        text_set = False
        for selector in textarea_selectors:
            result = await self.set_text(selector, text)
            if result:
                text_set = True
                logger.info(f"✅ Текст установлен через селектор: {selector}")
                break
        
        if not text_set:
            return False, "Не найдено поле ввода"
        
        await asyncio.sleep(0.5)
        
        # 2. Находим кнопку отправки (из JSON: cl="omni-button-content-btn")
        send_selectors = [
            '.omni-button-content-btn',  # основная кнопка из JSON
            'button[aria-label*="Голосовой режим"]',
            'button[aria-label*="Voice"]',
            '[role="button"] .icon-line-waveform',
            '.message-input-right-button-send'
        ]
        
        clicked = False
        for selector in send_selectors:
            result = await self.click_element(selector)
            if result:
                clicked = True
                logger.info(f"✅ Кнопка нажата через селектор: {selector}")
                break
        
        if not clicked:
            # Пробуем Enter
            enter_js = """
            (function() {
                var el = document.querySelector('.message-input-textarea, textarea[placeholder*="помочь"]');
                if (!el) return false;
                el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', bubbles: true}));
                el.dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', code: 'Enter', bubbles: true}));
                return true;
            })()
            """
            await self.evaluate(enter_js)
            logger.info("⏎ Нажат Enter")
        
        return True, "Сообщение отправлено"
    
    async def wait_for_response(self, timeout=90):
        """Ожидать ответ от Qwen"""
        js = f"""
        (function() {{
            var startTime = Date.now();
            var maxWait = {timeout * 1000};
            
            function findResponse() {{
                // Ищем последний ответ
                var selectors = [
                    '.message-content:not(:empty)',
                    '.chat-message:not(:empty)',
                    '[class*="message"]:not(:empty)',
                    '.ant-message'
                ];
                
                var allTexts = [];
                for (var s of selectors) {{
                    var els = document.querySelectorAll(s);
                    for (var i = 0; i < els.length; i++) {{
                        var text = (els[i].textContent || '').trim();
                        if (text && text.length > 10) {{
                            allTexts.push(text);
                        }}
                    }}
                }}
                
                // Возвращаем самый длинный текст (скорее всего ответ)
                if (allTexts.length > 0) {{
                    allTexts.sort(function(a, b) {{ return b.length - a.length; }});
                    return allTexts[0];
                }}
                return null;
            }}
            
            var lastResponse = null;
            while (Date.now() - startTime < maxWait) {{
                var response = findResponse();
                if (response && response !== lastResponse) {{
                    lastResponse = response;
                    // Если ответ длинный, вероятно это финальный ответ
                    if (response.length > 50) {{
                        return response;
                    }}
                }}
                
                // Проверяем, нет ли индикатора загрузки
                var loading = document.querySelector('[class*="loading"], [class*="typing"], .anticon-loading');
                if (!loading && response && response.length > 20) {{
                    return response;
                }}
                
                // Ждем 1 секунду
                var end = Date.now() + 1000;
                while (Date.now() < end) {{}}
            }}
            
            return lastResponse || null;
        }})()
        """
        return await self.evaluate(js)
    
    async def ask_qwen(self, question):
        """Задать вопрос Qwen"""
        try:
            # Открываем Qwen
            await self.navigate("https://chat.qwen.ai/")
            await self.wait_for_load(5)
            
            # Отправляем сообщение
            success, msg = await self.send_message_to_qwen(question)
            if not success:
                return None, msg
            
            # Ждем ответ
            response = await self.wait_for_response(90)
            
            if response:
                return response, None
            else:
                return None, "Не удалось получить ответ"
                
        except Exception as e:
            logger.error(f"Ошибка: {e}")
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
        f"📌 /clear — перезагрузить страницу",
        parse_mode='Markdown'
    )

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await browser.navigate("https://chat.qwen.ai/")
        await browser.wait_for_load(3)
        await update.message.reply_text("✅ Страница перезагружена")
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
            await status_msg.edit_text("❌ Не удалось получить ответ")
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Qwen Bot запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()