# bot.py - улучшенная версия с отслеживанием новых элементов
import os
import json
import asyncio
import logging
import httpx
import warnings
from datetime import datetime
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
# ФИЛЬТРЫ СИСТЕМНЫХ СООБЩЕНИЙ
# ============================================================

SYSTEM_PATTERNS = [
    'All chats', 'Today', 'Projects', 'New Project',
    'What can I do for you?', 'Voice Chat', 'Video Chat',
    'AutoChoose', 'Get Started', 'Please enter',
    'Что бы вы хотели', 'Log in', 'Sign up',
    'Скачать приложение', 'Войти', 'Завершено размышление',
    'Thinking completed', 'Выберите', 'Ваш выбор',
    'Qwen3.7-Plus', 'Новый чат', 'Сообщество', 'Coder',
    'Все чаты', 'Используя Qwen Studio',
    'Пользовательские условия', 'Политика конфиденциальности',
    'Сообщить', 'Первое изображение', 'Выберите один из образцов',
    'Welcome', 'Login', 'Sign up', 'Menu', 'Settings',
    'Profile', 'History', 'New Chat', 'Delete', 'Edit',
    'Share', 'Copy', 'Regenerate', 'Stop generating'
]

class A11YSnapshot:
    """Снимок Accessibility Tree для сравнения"""
    def __init__(self, elements):
        self.elements = elements
        self.texts = {el['text']: el for el in elements}
        self.timestamp = datetime.now()
    
    def find_new_elements(self, new_snapshot):
        """Найти элементы, которых не было в предыдущем снимке"""
        new_elements = []
        for el in new_snapshot.elements:
            # Проверяем, есть ли такой текст в предыдущем снимке
            if el['text'] not in self.texts:
                # Дополнительная проверка: не похож ли на существующий (похожие тексты)
                is_duplicate = False
                for existing_text in self.texts.keys():
                    # Если тексты сильно похожи (>80% совпадения)
                    if self._similarity(el['text'], existing_text) > 0.8:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    new_elements.append(el)
        
        return new_elements
    
    @staticmethod
    def _similarity(text1, text2):
        """Простая проверка похожести текстов"""
        if not text1 or not text2:
            return 0
        # Берем первые 50 символов для сравнения
        t1 = text1[:50].lower()
        t2 = text2[:50].lower()
        
        # Считаем совпадающие слова
        words1 = set(t1.split())
        words2 = set(t2.split())
        
        if not words1 or not words2:
            return 0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)

# ============================================================
# BROWSER HARNESS
# ============================================================

class BrowserHarness:
    def __init__(self, cdp_url="http://localhost:9222"):
        self.cdp_url = cdp_url
        self.ws_url = None
        self.last_snapshot = None
    
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
        """Парсинг Accessibility Tree на лету (улучшенная версия)"""
        js = """
        (function() {
            var results = [];
            var allElements = document.querySelectorAll('[role], div, span, p, h1, h2, h3, h4, h5, h6, li, td, th, label, button, a, article, section');
            
            for (var i = 0; i < allElements.length; i++) {
                var el = allElements[i];
                if (el.offsetParent === null) continue;
                
                var text = (el.textContent || '').trim();
                if (!text || text.length < 2) continue;
                
                var role = el.getAttribute('role') || el.tagName.toLowerCase();
                var ariaLabel = el.getAttribute('aria-label') || '';
                var className = el.className || '';
                var id = el.id || '';
                
                // Определяем тип элемента
                var elementType = 'text';
                if (role === 'button' || el.tagName === 'BUTTON') elementType = 'button';
                else if (role === 'input' || el.tagName === 'INPUT') elementType = 'input';
                else if (role === 'textarea' || el.tagName === 'TEXTAREA') elementType = 'textarea';
                else if (role === 'img' || el.tagName === 'IMG') elementType = 'image';
                else if (role === 'link' || el.tagName === 'A') elementType = 'link';
                else if (role === 'article' || el.tagName === 'ARTICLE') elementType = 'article';
                else if (role === 'section' || el.tagName === 'SECTION') elementType = 'section';
                
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
                
                // Проверяем на системные сообщения
                var systemPatterns = [
                    'All chats', 'Today', 'Projects', 'New Project',
                    'What can I do for you?', 'Voice Chat', 'Video Chat',
                    'AutoChoose', 'Get Started', 'Please enter',
                    'Что бы вы хотели', 'Log in', 'Sign up',
                    'Скачать приложение', 'Войти', 'Завершено размышление',
                    'Thinking completed', 'Выберите', 'Ваш выбор',
                    'Qwen3.7-Plus', 'Новый чат', 'Сообщество', 'Coder',
                    'Все чаты', 'Используя Qwen Studio',
                    'Пользовательские условия', 'Политика конфиденциальности',
                    'Сообщить', 'Первое изображение', 'Выберите один из образцов',
                    'Welcome', 'Login', 'Menu', 'Settings',
                    'Profile', 'History', 'New Chat', 'Delete', 'Edit',
                    'Share', 'Copy', 'Regenerate', 'Stop generating'
                ];
                
                var isSystem = false;
                for (var p of systemPatterns) {
                    if (text.includes(p)) {
                        isSystem = true;
                        break;
                    }
                }
                
                // Также проверяем по aria-label
                if (!isSystem) {
                    for (var p of systemPatterns) {
                        if (ariaLabel.includes(p)) {
                            isSystem = true;
                            break;
                        }
                    }
                }
                
                if (!isSystem) {
                    results.push({
                        text: text.slice(0, 500),
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
    
    async def get_snapshot(self):
        """Получить снимок A11Y"""
        elements = await self.parse_a11y_tree()
        return A11YSnapshot(elements)
    
    async def find_response_in_a11y(self, previous_snapshot=None, max_wait=60):
        """
        Найти ответ в A11Y дереве с отслеживанием новых элементов
        
        Args:
            previous_snapshot: Снимок ДО отправки вопроса
            max_wait: Максимальное время ожидания в секундах
        
        Returns:
            tuple: (ответ, найденные_элементы) или (None, None)
        """
        logger.info("🔍 Анализирую Accessibility Tree...")
        
        for attempt in range(max_wait):
            await asyncio.sleep(1)
            
            # Получаем текущий снимок
            current_snapshot = await self.get_snapshot()
            logger.info(f"📝 A11Y элементов сейчас: {len(current_snapshot.elements)}")
            
            # Если есть предыдущий снимок - ищем новые элементы
            if previous_snapshot:
                new_elements = previous_snapshot.find_new_elements(current_snapshot)
                
                if new_elements:
                    logger.info(f"🆕 Найдено {len(new_elements)} новых элементов")
                    
                    # Сортируем новые элементы по длине и типу
                    # Приоритет: article > section > text
                    priority_order = {'article': 3, 'section': 2, 'text': 1}
                    
                    sorted_elements = sorted(
                        new_elements,
                        key=lambda x: (
                            priority_order.get(x['elementType'], 0),
                            x['length']
                        ),
                        reverse=True
                    )
                    
                    # Ищем ответ среди новых элементов
                    for el in sorted_elements:
                        # Исключаем системные элементы
                        if el['elementType'] in ['button', 'input', 'textarea', 'link', 'image']:
                            continue
                        
                        # Проверяем на системные паттерны
                        is_system = False
                        for pattern in SYSTEM_PATTERNS:
                            if pattern.lower() in el['text'].lower():
                                is_system = True
                                break
                        
                        if is_system:
                            continue
                        
                        # Ответ должен быть достаточно длинным
                        if el['length'] > 30:
                            logger.info(f"✅ Найден потенциальный ответ:")
                            logger.info(f"   Текст: {el['text'][:100]}...")
                            logger.info(f"   Тип: {el['elementType']}, Роль: {el['role']}")
                            logger.info(f"   Длина: {el['length']}")
                            return el['text'], new_elements
            
            # Если прошло больше половины времени, проверяем все элементы (не только новые)
            if attempt > max_wait // 2 and not previous_snapshot:
                # Ищем самый длинный не-системный текст
                for el in current_snapshot.elements:
                    if el['elementType'] in ['button', 'input', 'textarea', 'link', 'image']:
                        continue
                    
                    is_system = False
                    for pattern in SYSTEM_PATTERNS:
                        if pattern.lower() in el['text'].lower():
                            is_system = True
                            break
                    
                    if not is_system and el['length'] > 50:
                        return el['text'], current_snapshot.elements
            
            if attempt % 10 == 0:
                logger.info(f"⏳ Ожидание ответа... {attempt}/{max_wait}с")
        
        return None, None
    
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
        """Задать вопрос и найти ответ через A11Y с отслеживанием новых элементов"""
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
            
            # ШАГ 3: Сохраняем снимок A11y ДО отправки
            logger.info("📸 Сохраняю снимок A11Y ДО отправки...")
            previous_snapshot = await self.get_snapshot()
            logger.info(f"📦 Сохранено {len(previous_snapshot.elements)} элементов до отправки")
            
            # ШАГ 4: Ввод текста
            logger.info(f"📌 Ввод текста: {question[:30]}...")
            result = await self.set_text(TEXTAREA_SELECTOR, question)
            
            if not result or not result.get('success'):
                return None, "Не удалось ввести текст"
            
            await self.wait_for_load(0.5)
            
            # ШАГ 5: Отправка
            logger.info("📤 Отправка сообщения...")
            
            # Пробуем кнопку отправки
            clicked = await self.click_element(SEND_BUTTON_SELECTOR)
            
            if not clicked:
                logger.info("⌨️ Кнопка не нажалась, пробую Enter...")
                await self.send_enter()
            
            await self.wait_for_load(2)
            
            # ШАГ 6: Поиск ответа через A11Y с отслеживанием новых элементов
            logger.info("⏳ Ожидание ответа...")
            response, new_elements = await self.find_response_in_a11y(
                previous_snapshot=previous_snapshot,
                max_wait=60
            )
            
            if response:
                return response, None
            
            return None, "Таймаут ожидания ответа (новых элементов не найдено)"
                
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
        f"🤖 **Qwen Bot v2 (A11Y + Diff)**\n\n"
        f"{cookies_status}\n\n"
        f"✅ Отслеживает НОВЫЕ элементы в A11Y\n"
        f"✅ Сравнивает снимки до и после отправки\n"
        f"✅ Фильтрует системные сообщения\n\n"
        f"📌 /debug — состояние\n"
        f"📌 /a11y — показать A11Y дерево\n"
        f"📌 /snapshot — показать снимок A11Y",
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

async def snapshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать снимок A11Y"""
    try:
        snapshot = await browser.get_snapshot()
        
        msg = f"📸 **Снимок A11Y ({len(snapshot.elements)} элементов)**\n\n"
        
        # Показываем топ-10 самых длинных текстов
        sorted_elements = sorted(snapshot.elements, key=lambda x: x['length'], reverse=True)
        
        for i, el in enumerate(sorted_elements[:10]):
            msg += f"{i+1}. {el['text'][:80]}...\n"
            msg += f"   Тип: {el['elementType']}, Длина: {el['length']}\n\n"
        
        await update.message.reply_text(msg[:4000], parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        title = await browser.evaluate("document.title")
        textarea_value = await browser.get_text_value(TEXTAREA_SELECTOR)
        
        # Получаем текущий снимок
        snapshot = await browser.get_snapshot()
        
        # Ищем потенциальный ответ (самый длинный текст)
        potential_answer = None
        for el in sorted(snapshot.elements, key=lambda x: x['length'], reverse=True):
            if el['length'] > 30 and el['elementType'] not in ['button', 'input', 'textarea']:
                potential_answer = el['text']
                break
        
        msg = f"🔍 **Отладка**\n\n"
        msg += f"Заголовок: {title}\n"
        msg += f"📝 Текст в поле: {textarea_value or 'пусто'}\n"
        msg += f"🌳 A11Y элементов: {len(snapshot.elements)}\n"
        msg += f"💬 Потенциальный ответ: {potential_answer[:200] if potential_answer else 'нет'}\n"
        msg += f"🍪 Кук: {len(COOKIES)}\n"
        msg += f"📸 Последний снимок: {snapshot.timestamp.strftime('%H:%M:%S')}\n"
        
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
            await status_msg.edit_text("❌ Нет ответа (возможно, Qwen еще думает)")
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
    app.add_handler(CommandHandler("snapshot", snapshot_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Qwen Bot v2 запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()