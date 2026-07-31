# bot.py - с расширенной отладкой
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
    level=logging.DEBUG,  # Включаем DEBUG для деталей
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

ELEMENTS = {
    'textarea': {
        'coords': [328, 167, 245, 56],
        'selector': '.message-input-textarea'
    },
    'send_button': {
        'coords': [720, 179, 32, 32],
        'selector': '.omni-button-content-btn'
    }
}

def get_center_coords(coords):
    x, y, w, h = coords
    return (x + w // 2, y + h // 2)

# ============================================================
# BROWSER HARNESS
# ============================================================

class BrowserHarness:
    def __init__(self, cdp_url="http://localhost:9222"):
        self.cdp_url = cdp_url
        self.ws_url = None
        self.last_debug = {}  # Для отладки
    
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
    
    async def evaluate(self, expression, log_result=True):
        """Выполнить JS и вернуть результат"""
        try:
            result = await self._send_cdp("Runtime.evaluate", {
                "expression": expression,
                "returnByValue": True
            })
            
            if "result" in result and "result" in result["result"]:
                value = result["result"]["result"].get("value")
                if log_result:
                    logger.debug(f"JS result: {str(value)[:100]}...")
                return value
            elif "error" in result:
                logger.error(f"JS error: {result['error']}")
                return None
            else:
                logger.warning(f"JS unexpected result: {result}")
                return None
        except Exception as e:
            logger.error(f"JS evaluate error: {e}")
            return None
    
    async def wait_for_load(self, timeout=5):
        logger.info(f"⏳ Ожидание {timeout}с...")
        await asyncio.sleep(timeout)
    
    # ============================================================
    # ДИАГНОСТИКА
    # ============================================================
    
    async def get_page_snapshot(self):
        """Получить снимок страницы для отладки"""
        snapshot = {}
        
        # 1. Заголовок
        snapshot['title'] = await self.evaluate("document.title")
        
        # 2. URL
        snapshot['url'] = await self.evaluate("window.location.href")
        
        # 3. Проверка элементов
        for name, element in ELEMENTS.items():
            selector = element['selector']
            exists = await self.evaluate(f"!!document.querySelector('{selector}')")
            snapshot[f'{name}_exists'] = exists
            
            if exists:
                # Получаем текст элемента
                text = await self.evaluate(f"""
                (function() {{
                    var el = document.querySelector('{selector}');
                    return el ? (el.textContent || '').trim() : null;
                }})()
                """)
                snapshot[f'{name}_text'] = text[:100] if text else None
        
        # 4. Количество сообщений
        snapshot['messages_count'] = await self.evaluate("""
        (function() {
            return document.querySelectorAll('.message-content, .chat-message').length;
        })()
        """)
        
        # 5. Последний ответ
        snapshot['last_response'] = await self.get_last_response()
        
        # 6. Есть ли индикатор загрузки
        snapshot['loading'] = await self.evaluate("""
        (function() {
            return !!document.querySelector('[class*="loading"], [class*="typing"], .anticon-loading');
        })()
        """)
        
        # 7. React Fiber на поле ввода
        snapshot['textarea_fiber'] = await self.evaluate("""
        (function() {
            var el = document.querySelector('.message-input-textarea');
            if (!el) return null;
            for (var key in el) {
                if (key.indexOf('__reactFiber') === 0 || key.indexOf('__reactInternalInstance') === 0) {
                    return key;
                }
            }
            return null;
        })()
        """)
        
        self.last_debug = snapshot
        return snapshot
    
    # ============================================================
    # КЛИКИ
    # ============================================================
    
    async def click_method_1_cdp(self, x, y):
        """Способ 1: CDP mouse events"""
        logger.info("  [1] CDP mouse events...")
        try:
            # mouseMoved
            result = await self._send_cdp("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": x,
                "y": y
            })
            if "error" in result:
                logger.warning(f"  [1] mouseMoved error: {result['error']}")
                return False
            
            await asyncio.sleep(0.05)
            
            # mousePressed
            result = await self._send_cdp("Input.dispatchMouseEvent", {
                "type": "mousePressed",
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1
            })
            if "error" in result:
                logger.warning(f"  [1] mousePressed error: {result['error']}")
                return False
            
            await asyncio.sleep(0.05)
            
            # mouseReleased
            result = await self._send_cdp("Input.dispatchMouseEvent", {
                "type": "mouseReleased",
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1
            })
            if "error" in result:
                logger.warning(f"  [1] mouseReleased error: {result['error']}")
                return False
            
            logger.info("  ✅ [1] CDP клик сработал")
            return True
        except Exception as e:
            logger.warning(f"  ❌ [1] CDP клик ошибка: {e}")
            return False
    
    async def click_method_2_js(self, selector):
        """Способ 2: JavaScript click"""
        logger.info(f"  [2] JavaScript click...")
        try:
            result = await self.evaluate(f"""
            (function() {{
                var el = document.querySelector('{selector}');
                if (!el) {{
                    console.log('Element not found: {selector}');
                    return false;
                }}
                el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                el.click();
                return true;
            }})()
            """)
            if result:
                logger.info("  ✅ [2] JS клик сработал")
                return True
            else:
                logger.warning("  ❌ [2] JS клик вернул false")
                return False
        except Exception as e:
            logger.warning(f"  ❌ [2] JS клик ошибка: {e}")
            return False
    
    async def click_method_3_react_onclick(self, selector):
        """Способ 3: React onClick props"""
        logger.info("  [3] React onClick...")
        try:
            result = await self.evaluate(f"""
            (function() {{
                var el = document.querySelector('{selector}');
                if (!el) return false;
                
                // Ищем React Fiber
                var fiberKey = null;
                for (var key in el) {{
                    if (key.indexOf('__reactFiber') === 0 || key.indexOf('__reactInternalInstance') === 0) {{
                        fiberKey = key;
                        break;
                    }}
                }}
                
                if (!fiberKey) return false;
                
                var fiber = el[fiberKey];
                var handler = null;
                
                while (fiber) {{
                    if (fiber.memoizedProps) {{
                        if (fiber.memoizedProps.onClick) {{
                            handler = fiber.memoizedProps.onClick;
                            break;
                        }}
                        if (fiber.memoizedProps.onMouseDown) {{
                            handler = fiber.memoizedProps.onMouseDown;
                            break;
                        }}
                    }}
                    fiber = fiber.return;
                }}
                
                if (handler) {{
                    handler({{ target: el, currentTarget: el, type: 'click', bubbles: true }});
                    return true;
                }}
                return false;
            }})()
            """)
            if result:
                logger.info("  ✅ [3] React onClick сработал")
                return True
            else:
                logger.warning("  ❌ [3] React onClick не найден")
                return False
        except Exception as e:
            logger.warning(f"  ❌ [3] React onClick ошибка: {e}")
            return False
    
    async def click_method_4_react_onchange(self, selector):
        """Способ 4: React onChange (для полей ввода)"""
        if 'textarea' not in selector and 'input' not in selector:
            return False
        
        logger.info("  [4] React onChange...")
        try:
            result = await self.evaluate(f"""
            (function() {{
                var el = document.querySelector('{selector}');
                if (!el) return false;
                
                var fiberKey = null;
                for (var key in el) {{
                    if (key.indexOf('__reactFiber') === 0 || key.indexOf('__reactInternalInstance') === 0) {{
                        fiberKey = key;
                        break;
                    }}
                }}
                
                if (!fiberKey) return false;
                
                var fiber = el[fiberKey];
                var handler = null;
                
                while (fiber) {{
                    if (fiber.memoizedProps && fiber.memoizedProps.onChange) {{
                        handler = fiber.memoizedProps.onChange;
                        break;
                    }}
                    fiber = fiber.return;
                }}
                
                if (handler) {{
                    el.value = el.value;
                    handler({{ target: el, type: 'change', bubbles: true }});
                    return true;
                }}
                return false;
            }})()
            """)
            if result:
                logger.info("  ✅ [4] React onChange сработал")
                return True
            else:
                logger.warning("  ❌ [4] React onChange не найден")
                return False
        except Exception as e:
            logger.warning(f"  ❌ [4] React onChange ошибка: {e}")
            return False
    
    async def click_react(self, selector, x, y):
        """Универсальный клик - пробуем все способы"""
        logger.info(f"🖱️ Клик по {selector} в ({x}, {y})")
        
        methods = [
            ("CDP mouse events", lambda: self.click_method_1_cdp(x, y)),
            ("JavaScript click", lambda: self.click_method_2_js(selector)),
            ("React onClick", lambda: self.click_method_3_react_onclick(selector)),
            ("React onChange", lambda: self.click_method_4_react_onchange(selector)),
        ]
        
        for name, method in methods:
            result = await method()
            if result:
                logger.info(f"✅ Клик выполнен через: {name}")
                return True
        
        logger.error("❌ Все методы клика не сработали!")
        return False
    
    # ============================================================
    # РАБОТА С ТЕКСТОМ
    # ============================================================
    
    async def set_text_react(self, selector, text):
        """Установить текст с поддержкой React"""
        logger.info(f"✏️ Ввод текста в {selector}")
        
        result = await self.evaluate(f"""
        (function() {{
            var el = document.querySelector('{selector}');
            if (!el) {{
                console.log('Element not found: {selector}');
                return false;
            }}
            
            el.focus();
            el.click();
            el.value = '';
            el.value = '{text.replace("'", "\\'")}';
            
            // Триггерим все события
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            el.dispatchEvent(new Event('keydown', {{ bubbles: true }}));
            el.dispatchEvent(new Event('keyup', {{ bubbles: true }}));
            
            // Пробуем React onChange
            var fiberKey = null;
            for (var key in el) {{
                if (key.indexOf('__reactFiber') === 0 || key.indexOf('__reactInternalInstance') === 0) {{
                    fiberKey = key;
                    break;
                }}
            }}
            
            if (fiberKey) {{
                var fiber = el[fiberKey];
                while (fiber) {{
                    if (fiber.memoizedProps && fiber.memoizedProps.onChange) {{
                        fiber.memoizedProps.onChange({{ target: el, type: 'change', bubbles: true }});
                        break;
                    }}
                    fiber = fiber.return;
                }}
            }}
            
            // Дополнительно: пробуем onInput
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            
            return true;
        }})()
        """)
        
        if result:
            logger.info("✅ Текст установлен")
        else:
            logger.warning("❌ Не удалось установить текст")
        
        return result
    
    # ============================================================
    # ПОЛУЧЕНИЕ ОТВЕТА
    # ============================================================
    
    async def get_last_response(self):
        """Получить последний ответ"""
        return await self.evaluate("""
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
        """)
    
    # ============================================================
    # ОСНОВНАЯ ФУНКЦИЯ
    # ============================================================
    
    async def ask_qwen(self, question):
        """Запрос к Qwen с полной отладкой"""
        try:
            # Переход на сайт
            logger.info("🚀 Переход на chat.qwen.ai...")
            await self.navigate("https://chat.qwen.ai/")
            await self.wait_for_load(5)
            
            # Делаем снимок страницы
            logger.info("📸 Делаю снимок страницы...")
            snapshot = await self.get_page_snapshot()
            logger.info(f"  Заголовок: {snapshot.get('title')}")
            logger.info(f"  Поле ввода: {'есть' if snapshot.get('textarea_exists') else 'нет'}")
            logger.info(f"  Кнопка отправки: {'есть' if snapshot.get('send_button_exists') else 'нет'}")
            logger.info(f"  Сообщений: {snapshot.get('messages_count')}")
            logger.info(f"  React Fiber: {snapshot.get('textarea_fiber')}")
            
            # ============================================================
            # ШАГ 1: Ввод текста
            # ============================================================
            textarea_selector = ELEMENTS['textarea']['selector']
            
            logger.info("📌 ШАГ 1: Ввод текста...")
            text_set = await self.set_text_react(textarea_selector, question)
            
            if not text_set:
                return None, "Не удалось ввести текст"
            
            await self.wait_for_load(1)
            
            # Снова проверяем появилась ли кнопка
            send_exists = await self.evaluate(f"!!document.querySelector('{ELEMENTS['send_button']['selector']}')")
            logger.info(f"  Кнопка отправки после ввода: {'есть' if send_exists else 'нет'}")
            
            # ============================================================
            # ШАГ 2: Отправка
            # ============================================================
            send_selector = ELEMENTS['send_button']['selector']
            send_coords = ELEMENTS['send_button']['coords']
            sx, sy = get_center_coords(send_coords)
            
            if send_exists:
                logger.info("📌 ШАГ 2: Клик по кнопке отправки...")
                clicked = await self.click_react(send_selector, sx, sy)
                if not clicked:
                    logger.warning("⚠️ Клик не сработал, пробую Enter...")
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
            else:
                logger.info("⏳ Кнопка не появилась, пробую Enter...")
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
            
            # ============================================================
            # ШАГ 3: Ожидание ответа
            # ============================================================
            logger.info("⏳ ШАГ 3: Ожидание ответа...")
            max_attempts = 120
            
            for attempt in range(max_attempts):
                await asyncio.sleep(1)
                
                response = await self.get_last_response()
                
                if response:
                    logger.info(f"✅ Получен ответ: {response[:50]}...")
                    return response, None
                
                # Проверяем индикатор загрузки
                if attempt % 5 == 0:
                    loading = await self.evaluate("""
                    (function() {
                        return !!document.querySelector('[class*="loading"], [class*="typing"], .anticon-loading');
                    })()
                    """)
                    logger.info(f"⏳ Ожидание... {attempt}/{max_attempts}, загрузка: {'да' if loading else 'нет'}")
            
            # Если ничего не нашли, делаем финальный снимок
            final_snapshot = await self.get_page_snapshot()
            logger.info(f"📸 Финальный снимок: {json.dumps(final_snapshot, indent=2, default=str)[:500]}")
            
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
        f"С расширенной отладкой!\n"
        f"Пробует 4 способа клика:\n"
        f"1. CDP mouse events\n"
        f"2. JavaScript click\n"
        f"3. React onClick\n"
        f"4. React onChange\n\n"
        f"📌 /debug — детальная отладка\n"
        f"📌 /snapshot — снимок страницы"
    )

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детальная отладка"""
    try:
        snapshot = await browser.get_page_snapshot()
        
        msg = "🔍 **Отладка**\n\n"
        for key, value in snapshot.items():
            if value is not None:
                if isinstance(value, str) and len(value) > 100:
                    value = value[:100] + "..."
                msg += f"**{key}:** {value}\n"
        
        # Отправляем в Markdown
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def snapshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полный снимок страницы"""
    try:
        snapshot = await browser.get_page_snapshot()
        # Сохраняем в файл
        filename = "snapshot.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, indent=2, default=str, ensure_ascii=False)
        
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption="📸 Снимок страницы"
            )
        
        os.remove(filename)
        
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
    app.add_handler(CommandHandler("snapshot", snapshot_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Qwen Bot запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()