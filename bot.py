import asyncio
import logging
import os
import json
import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.constants import Key, PageLoadState, MouseButton

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
AGNES_API_URL = os.environ.get("AGNES_API_URL", "https://api.agnes.ai/v1")
CHROME_PATH = os.environ.get("CHROME_PATH", "/usr/bin/google-chrome")

if not TOKEN or not AGNES_API_KEY:
    raise ValueError("TELEGRAM_BOT_TOKEN или AGNES_API_KEY не установлены!")

user_browsers = {}

class BrowserAgent:
    """Агент для управления браузером через Pydoll - ВСЕ КОМАНДЫ ИЗ ДОКУМЕНТАЦИИ"""
    
    def __init__(self):
        self.browser = None
        self.tab = None
        self.is_running = False
        
    async def start(self):
        """Запуск браузера с настройками из документации"""
        if self.is_running:
            return self
            
        options = ChromiumOptions()
        options.binary_location = CHROME_PATH
        options.headless = True
        options.start_timeout = 30
        options.page_load_state = PageLoadState.INTERACTIVE
        
        # Аргументы из документации для Docker
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-plugins')
        options.add_argument('--disable-images')
        options.add_argument('--disable-javascript')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--disable-web-security')
        
        self.browser = Chrome(options=options)
        await self.browser.start()
        self.tab = await self.browser.get_tab()
        self.is_running = True
        
        logger.info("✅ Браузер запущен")
        return self
    
    async def execute(self, action: str, params: dict = None):
        """Выполняет действия - ВСЕ команды из документации Pydoll"""
        if not self.is_running:
            await self.start()
            
        params = params or {}
        
        actions = {
            # === НАВИГАЦИЯ ===
            "go_to": self._go_to,
            "back": self._back,
            "forward": self._forward,
            "refresh": self._refresh,
            "get_title": self._get_title,
            "get_url": self._get_url,
            "get_html": self._get_html,
            
            # === ПОИСК ЭЛЕМЕНТОВ ===
            "find": self._find,
            "find_all": self._find_all,
            "find_shadow_roots": self._find_shadow_roots,
            "find_shadow_root": self._find_shadow_root,
            
            # === ВЗАИМОДЕЙСТВИЕ С ЭЛЕМЕНТАМИ ===
            "click": self._click,
            "click_js": self._click_js,
            "type": self._type,
            "type_human": self._type_human,
            "scroll": self._scroll,
            "scroll_to": self._scroll_to,
            "screenshot": self._screenshot,
            "get_text": self._get_text,
            "get_attribute": self._get_attribute,
            "get_value": self._get_value,
            
            # === КЛАВИАТУРА ===
            "press_key": self._press_key,
            "type_key": self._type_key,
            "press_enter": self._press_enter,
            "press_tab": self._press_tab,
            
            # === МЫШЬ ===
            "mouse_move": self._mouse_move,
            "mouse_click": self._mouse_click,
            "mouse_double_click": self._mouse_double_click,
            "mouse_right_click": self._mouse_right_click,
            
            # === ВКЛАДКИ ===
            "new_tab": self._new_tab,
            "switch_tab": self._switch_tab,
            "close_tab": self._close_tab,
            "get_tabs": self._get_tabs,
            
            # === IFRAME ===
            "switch_iframe": self._switch_iframe,
            "exit_iframe": self._exit_iframe,
            
            # === JAVASCRIPT ===
            "execute_script": self._execute_script,
            "execute_async_script": self._execute_async_script,
            
            # === ОЖИДАНИЕ ===
            "wait": self._wait,
            "wait_for": self._wait_for,
            
            # === КУКИ ===
            "get_cookies": self._get_cookies,
            "set_cookies": self._set_cookies,
            "delete_cookies": self._delete_cookies,
            
            # === LOCAL STORAGE ===
            "get_local_storage": self._get_local_storage,
            "set_local_storage": self._set_local_storage,
            "clear_local_storage": self._clear_local_storage,
            
            # === SESSION STORAGE ===
            "get_session_storage": self._get_session_storage,
            "set_session_storage": self._set_session_storage,
            "clear_session_storage": self._clear_session_storage,
            
            # === ДРУГИЕ ===
            "get_page_source": self._get_page_source,
            "get_page_content": self._get_page_content,
            "get_page_html": self._get_page_html,
            "screenshot_element": self._screenshot_element,
            "screenshot_full_page": self._screenshot_full_page,
            "get_element_position": self._get_element_position,
            "get_element_size": self._get_element_size,
            "get_element_rect": self._get_element_rect,
            
            # === ВЫДЕЛЕНИЕ ТЕКСТА ===
            "select_text": self._select_text,
            "select_all": self._select_all,
            "copy_text": self._copy_text,
            
            # === ФОРМЫ ===
            "submit_form": self._submit_form,
            "clear_field": self._clear_field,
            
            # === СКРОЛЛ ===
            "scroll_to_element": self._scroll_to_element,
            "scroll_into_view": self._scroll_into_view,
            "scroll_by": self._scroll_by,
        }
        
        if action not in actions:
            raise ValueError(f"Неизвестное действие: {action}")
        
        return await actions[action](**params)
    
    # === РЕАЛИЗАЦИЯ ВСЕХ КОМАНД ===
    
    # --- Навигация ---
    async def _go_to(self, url: str):
        await self.tab.go_to(url)
        return f"✅ Перешел на {url}"
    
    async def _back(self):
        await self.tab.back()
        return "⬅️ Назад"
    
    async def _forward(self):
        await self.tab.forward()
        return "➡️ Вперед"
    
    async def _refresh(self):
        await self.tab.refresh()
        return "🔄 Обновлено"
    
    async def _get_title(self):
        title = await self.tab.title
        return f"📄 {title}"
    
    async def _get_url(self):
        url = await self.tab.current_url
        return f"🔗 {url}"
    
    async def _get_html(self):
        html = await self.tab.page_source
        return html[:2000]
    
    # --- Поиск элементов ---
    async def _find(self, selector: str):
        """Поиск элемента по CSS или XPath"""
        element = await self.tab.find(selector)
        if element:
            text = await element.text
            return f"🔍 Найден: {text[:100]}"
        return f"❌ Элемент {selector} не найден"
    
    async def _find_all(self, selector: str):
        """Поиск всех элементов"""
        elements = await self.tab.find_all(selector)
        return f"🔍 Найдено {len(elements)} элементов"
    
    async def _find_shadow_roots(self, deep: bool = False):
        """Поиск shadow roots"""
        roots = await self.tab.find_shadow_roots(deep=deep)
        return f"🌓 Найдено {len(roots)} shadow root'ов"
    
    async def _find_shadow_root(self, selector: str):
        """Поиск shadow root"""
        root = await self.tab.find_shadow_root(selector)
        return f"🌓 Найден shadow root: {selector}" if root else "❌ Не найден"
    
    # --- Взаимодействие ---
    async def _click(self, selector: str):
        """Клик с эмуляцией"""
        element = await self.tab.find(selector)
        if element:
            await element.click(humanize=True)
            return f"✅ Кликнул по {selector}"
        return f"❌ Элемент {selector} не найден"
    
    async def _click_js(self, selector: str):
        """Клик через JavaScript"""
        element = await self.tab.find(selector)
        if element:
            await element.click_using_js()
            return f"✅ Кликнул (JS) по {selector}"
        return f"❌ Элемент {selector} не найден"
    
    async def _type(self, selector: str, text: str):
        """Быстрый ввод"""
        element = await self.tab.find(selector)
        if element:
            await element.insert_text(text)
            return f"✅ Ввел '{text}' в {selector}"
        return f"❌ Элемент {selector} не найден"
    
    async def _type_human(self, selector: str, text: str):
        """Ввод с эмуляцией человека"""
        element = await self.tab.find(selector)
        if element:
            await element.type_text(text, humanize=True)
            return f"✅ Ввел '{text}' (humanized) в {selector}"
        return f"❌ Элемент {selector} не найден"
    
    async def _scroll(self, amount: int = 500):
        await self.tab.execute_script(f"window.scrollBy(0, {amount});")
        return f"✅ Прокрутил на {amount}px"
    
    async def _scroll_to(self, x: int = 0, y: int = 0):
        await self.tab.execute_script(f"window.scrollTo({x}, {y});")
        return f"✅ Прокрутил к ({x}, {y})"
    
    async def _screenshot(self):
        screenshot = await self.tab.screenshot()
        return screenshot
    
    async def _get_text(self, selector: str = None):
        if selector:
            element = await self.tab.find(selector)
            if element:
                text = await element.text
                return text[:500] if text else "Текст не найден"
            return f"❌ Элемент {selector} не найден"
        text = await self.tab.text
        return text[:500] if text else "Текст не найден"
    
    async def _get_attribute(self, selector: str, attribute: str):
        element = await self.tab.find(selector)
        if element:
            value = await element.get_attribute(attribute)
            return f"📋 {attribute}: {value}"
        return f"❌ Элемент {selector} не найден"
    
    async def _get_value(self, selector: str):
        element = await self.tab.find(selector)
        if element:
            value = await element.get_value()
            return f"📋 Значение: {value}"
        return f"❌ Элемент {selector} не найден"
    
    # --- Клавиатура ---
    async def _press_key(self, key: str):
        await self.tab.keyboard.press(getattr(Key, key.upper(), Key.ENTER))
        return f"⌨️ Нажал {key}"
    
    async def _type_key(self, key: str):
        await self.tab.keyboard.type(key)
        return f"⌨️ Ввел {key}"
    
    async def _press_enter(self):
        await self.tab.keyboard.press(Key.ENTER)
        return "⌨️ Нажал Enter"
    
    async def _press_tab(self):
        await self.tab.keyboard.press(Key.TAB)
        return "⌨️ Нажал Tab"
    
    # --- Мышь ---
    async def _mouse_move(self, x: int, y: int):
        await self.tab.mouse.move(x, y, humanize=True)
        return f"🖱️ Переместил мышь на ({x}, {y})"
    
    async def _mouse_click(self, x: int, y: int):
        await self.tab.mouse.click(x, y, humanize=True)
        return f"🖱️ Кликнул по ({x}, {y})"
    
    async def _mouse_double_click(self, x: int, y: int):
        await self.tab.mouse.double_click(x, y, humanize=True)
        return f"🖱️ Двойной клик по ({x}, {y})"
    
    async def _mouse_right_click(self, x: int, y: int):
        await self.tab.mouse.right_click(x, y, humanize=True)
        return f"🖱️ ПКМ по ({x}, {y})"
    
    # --- Вкладки ---
    async def _new_tab(self, url: str = None):
        self.tab = await self.browser.new_tab()
        if url:
            await self.tab.go_to(url)
            return f"✅ Новая вкладка: {url}"
        return "✅ Новая вкладка создана"
    
    async def _switch_tab(self, index: int):
        tabs = await self.browser.get_tabs()
        if 0 <= index < len(tabs):
            self.tab = tabs[index]
            return f"✅ Переключился на вкладку {index}"
        return f"❌ Вкладка {index} не найдена"
    
    async def _close_tab(self):
        await self.tab.close()
        self.is_running = False
        return "✅ Вкладка закрыта"
    
    async def _get_tabs(self):
        tabs = await self.browser.get_tabs()
        return f"📑 Вкладок: {len(tabs)}"
    
    # --- iframe ---
    async def _switch_iframe(self, selector: str):
        element = await self.tab.find(selector)
        if element:
            self.tab = await self.tab.get_frame(element)
            return "✅ Переключился в iframe"
        return f"❌ iframe {selector} не найден"
    
    async def _exit_iframe(self):
        self.tab = await self.tab.exit_frame()
        return "✅ Вышел из iframe"
    
    # --- JavaScript ---
    async def _execute_script(self, script: str):
        result = await self.tab.execute_script(script)
        return f"✅ JS: {str(result)[:200]}"
    
    async def _execute_async_script(self, script: str, args: list = None):
        result = await self.tab.execute_async_script(script, args or [])
        return f"✅ Async JS: {str(result)[:200]}"
    
    # --- Ожидание ---
    async def _wait(self, seconds: int = 2):
        await asyncio.sleep(seconds)
        return f"⏳ Подождал {seconds} сек"
    
    async def _wait_for(self, selector: str, timeout: int = 10):
        element = await self.tab.wait_for(selector, timeout=timeout)
        if element:
            return f"✅ Элемент {selector} появился"
        return f"❌ Элемент {selector} не появился"
    
    # --- Куки ---
    async def _get_cookies(self):
        cookies = await self.tab.get_cookies()
        return f"🍪 Куки: {json.dumps(cookies, indent=2)[:500]}"
    
    async def _set_cookies(self, cookies: list):
        await self.tab.set_cookies(cookies)
        return "✅ Куки установлены"
    
    async def _delete_cookies(self):
        await self.tab.delete_all_cookies()
        return "🗑️ Куки удалены"
    
    # --- Local Storage ---
    async def _get_local_storage(self, key: str = None):
        if key:
            value = await self.tab.get_local_storage(key)
            return f"📦 {key}: {value}"
        items = await self.tab.get_all_local_storage()
        return f"📦 Local Storage: {json.dumps(items, indent=2)[:500]}"
    
    async def _set_local_storage(self, key: str, value: str):
        await self.tab.set_local_storage(key, value)
        return f"✅ {key} = {value}"
    
    async def _clear_local_storage(self):
        await self.tab.clear_local_storage()
        return "🗑️ Local Storage очищен"
    
    # --- Session Storage ---
    async def _get_session_storage(self, key: str = None):
        if key:
            value = await self.tab.get_session_storage(key)
            return f"📦 {key}: {value}"
        items = await self.tab.get_all_session_storage()
        return f"📦 Session Storage: {json.dumps(items, indent=2)[:500]}"
    
    async def _set_session_storage(self, key: str, value: str):
        await self.tab.set_session_storage(key, value)
        return f"✅ {key} = {value}"
    
    async def _clear_session_storage(self):
        await self.tab.clear_session_storage()
        return "🗑️ Session Storage очищен"
    
    # --- Другие ---
    async def _get_page_source(self):
        source = await self.tab.page_source
        return source[:2000]
    
    async def _get_page_content(self):
        content = await self.tab.page_content
        return content[:2000]
    
    async def _get_page_html(self):
        html = await self.tab.page_html
        return html[:2000]
    
    async def _screenshot_element(self, selector: str):
        element = await self.tab.find(selector)
        if element:
            screenshot = await element.screenshot()
            return screenshot
        return f"❌ Элемент {selector} не найден"
    
    async def _screenshot_full_page(self):
        screenshot = await self.tab.screenshot(full_page=True)
        return screenshot
    
    async def _get_element_position(self, selector: str):
        element = await self.tab.find(selector)
        if element:
            pos = await element.get_position()
            return f"📍 Позиция: {pos}"
        return f"❌ Элемент {selector} не найден"
    
    async def _get_element_size(self, selector: str):
        element = await self.tab.find(selector)
        if element:
            size = await element.get_size()
            return f"📐 Размер: {size}"
        return f"❌ Элемент {selector} не найден"
    
    async def _get_element_rect(self, selector: str):
        element = await self.tab.find(selector)
        if element:
            rect = await element.get_rect()
            return f"📏 Rect: {rect}"
        return f"❌ Элемент {selector} не найден"
    
    # --- Выделение текста ---
    async def _select_text(self, selector: str):
        element = await self.tab.find(selector)
        if element:
            await element.select_text()
            return f"✅ Выделил текст в {selector}"
        return f"❌ Элемент {selector} не найден"
    
    async def _select_all(self):
        await self.tab.keyboard.press(Key.CONTROL, 'a')
        return "✅ Выделил всё"
    
    async def _copy_text(self):
        await self.tab.keyboard.press(Key.CONTROL, 'c')
        return "✅ Скопировал"
    
    # --- Формы ---
    async def _submit_form(self, selector: str = None):
        if selector:
            element = await self.tab.find(selector)
            if element:
                await element.submit()
                return f"✅ Отправил форму {selector}"
            return f"❌ Элемент {selector} не найден"
        await self.tab.keyboard.press(Key.ENTER)
        return "✅ Отправил форму"
    
    async def _clear_field(self, selector: str):
        element = await self.tab.find(selector)
        if element:
            await element.clear()
            return f"✅ Очистил {selector}"
        return f"❌ Элемент {selector} не найден"
    
    # --- Скролл ---
    async def _scroll_to_element(self, selector: str):
        element = await self.tab.find(selector)
        if element:
            await element.scroll_to()
            return f"✅ Прокрутил к {selector}"
        return f"❌ Элемент {selector} не найден"
    
    async def _scroll_into_view(self, selector: str):
        element = await self.tab.find(selector)
        if element:
            await element.scroll_into_view()
            return f"✅ Прокрутил к {selector}"
        return f"❌ Элемент {selector} не найден"
    
    async def _scroll_by(self, amount: int = 500):
        await self.tab.scroll_by(amount)
        return f"✅ Прокрутил на {amount}px"
    
    async def close(self):
        if self.browser and self.is_running:
            await self.browser.close()
            self.is_running = False
            logger.info("✅ Браузер закрыт")


# === AGNES AI ИНТЕГРАЦИЯ ===

async def ask_agnes(prompt: str):
    """Запрос к Agnes AI API"""
    async with aiohttp.ClientSession() as session:
        headers = {
            "Authorization": f"Bearer {AGNES_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "agnes-v1",
            "messages": [
                {"role": "system", "content": """Ты AI-агент, управляющий браузером через Pydoll.
                Преобразуй команду пользователя в JSON массив действий.
                ВСЕ действия доступны в документации Pydoll.
                Отвечай ТОЛЬКО JSON массивом."""},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        
        try:
            async with session.post(f"{AGNES_API_URL}/chat/completions", 
                                   headers=headers, 
                                   json=data,
                                   timeout=30) as response:
                if response.status == 200:
                    result = await response.json()
                    return result['choices'][0]['message']['content']
                else:
                    logger.error(f"Ошибка Agnes API: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Ошибка Agnes: {e}")
            return None

async def ai_parse_command(text: str):
    """Парсит команду через Agnes AI"""
    prompt = f"""
    Команда: "{text}"
    
    Все доступные действия (согласно документации Pydoll):
    
    НАВИГАЦИЯ: go_to, back, forward, refresh, get_title, get_url, get_html
    ПОИСК: find, find_all, find_shadow_roots
    ВЗАИМОДЕЙСТВИЕ: click, click_js, type, type_human, scroll, screenshot, get_text, get_attribute, get_value
    КЛАВИАТУРА: press_key, press_enter, press_tab
    МЫШЬ: mouse_move, mouse_click, mouse_double_click, mouse_right_click
    ВКЛАДКИ: new_tab, switch_tab, close_tab
    IFRAME: switch_iframe, exit_iframe
    JS: execute_script, execute_async_script
    ОЖИДАНИЕ: wait, wait_for
    КУКИ: get_cookies, set_cookies, delete_cookies
    STORAGE: get_local_storage, set_local_storage, clear_local_storage, get_session_storage, set_session_storage, clear_session_storage
    ФОРМЫ: submit_form, clear_field
    СКРОЛЛ: scroll_to_element, scroll_into_view
    
    Ответь JSON массивом действий.
    """
    
    response = await ask_agnes(prompt)
    if response:
        try:
            response = response.strip()
            if response.startswith('```json'):
                response = response[7:]
            if response.startswith('```'):
                response = response[3:]
            if response.endswith('```'):
                response = response[:-3]
            actions = json.loads(response.strip())
            return actions if isinstance(actions, list) else [actions]
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка JSON: {e}")
            return [{"action": "get_title"}]
    return [{"action": "get_title"}]


# === TELEGRAM БОТ ===

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    status_msg = await update.message.reply_text("🤖 Анализирую команду...")
    
    try:
        actions = await ai_parse_command(text)
        await status_msg.edit_text(f"📋 План: {len(actions)} шагов")
        
        if user_id not in user_browsers:
            user_browsers[user_id] = BrowserAgent()
            await user_browsers[user_id].start()
        
        agent = user_browsers[user_id]
        results = []
        screenshot_sent = False
        
        for i, action_data in enumerate(actions, 1):
            action = action_data.get("action")
            params = action_data.get("params", {})
            
            await status_msg.edit_text(f"🔄 Шаг {i}: {action}")
            
            try:
                result = await agent.execute(action, params)
                
                if action in ["screenshot", "screenshot_element", "screenshot_full_page"] and result:
                    await update.message.reply_photo(result)
                    screenshot_sent = True
                elif result:
                    result_str = str(result)
                    if len(result_str) > 500:
                        result_str = result_str[:500] + "..."
                    results.append(result_str)
                    
            except Exception as e:
                await update.message.reply_text(f"⚠️ Ошибка в шаге {i}: {str(e)}")
                logger.error(f"Ошибка: {e}")
        
        if screenshot_sent and not results:
            await status_msg.edit_text("✅ Скриншот отправлен!")
        elif results:
            await status_msg.edit_text(f"✅ Результат:\n\n{' '.join(results)}")
        else:
            await status_msg.edit_text("✅ Готово!")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **AI-агент Pydoll - ВСЕ КОМАНДЫ**\n\n"
        "📖 **Полный список доступных действий:**\n"
        "• **Навигация:** go_to, back, forward, refresh, get_title, get_url, get_html\n"
        "• **Поиск:** find, find_all, find_shadow_roots\n"
        "• **Клики:** click, click_js\n"
        "• **Ввод:** type, type_human\n"
        "• **Скролл:** scroll, scroll_to, scroll_to_element, scroll_into_view\n"
        "• **Скриншоты:** screenshot, screenshot_element, screenshot_full_page\n"
        "• **Текст:** get_text, get_attribute, get_value\n"
        "• **Клавиатура:** press_key, press_enter, press_tab\n"
        "• **Мышь:** mouse_move, mouse_click, mouse_double_click, mouse_right_click\n"
        "• **Вкладки:** new_tab, switch_tab, close_tab\n"
        "• **iframe:** switch_iframe, exit_iframe\n"
        "• **JS:** execute_script, execute_async_script\n"
        "• **Ожидание:** wait, wait_for\n"
        "• **Куки:** get_cookies, set_cookies, delete_cookies\n"
        "• **Storage:** get/set/clear local/session storage\n"
        "• **Формы:** submit_form, clear_field\n\n"
        "📝 **Примеры:**\n"
        "• Открой google.com и найди новости\n"
        "• Сделай скриншот youtube.com\n"
        "• Найди цену на iphone\n"
        "• Прокрути страницу и сделай скриншот\n"
        "• Введи Python в поиск и нажми Enter\n"
        "• Найди все ссылки на странице\n\n"
        "💡 **Просто напиши, что нужно сделать!**",
        parse_mode='Markdown'
    )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_browsers:
        await user_browsers[user_id].close()
        del user_browsers[user_id]
        await update.message.reply_text("🛑 Браузер закрыт!")
    else:
        await update.message.reply_text("❌ Нет активного браузера")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_browsers:
        agent = user_browsers[user_id]
        if agent.is_running:
            try:
                url = await agent.tab.current_url
                title = await agent.tab.title
                await update.message.reply_text(
                    f"✅ **Браузер активен**\n\n"
                    f"🔗 URL: {url}\n"
                    f"📄 {title}",
                    parse_mode='Markdown'
                )
            except:
                await update.message.reply_text("✅ Браузер активен")
        else:
            await update.message.reply_text("🔄 Браузер запускается...")
    else:
        await update.message.reply_text("❌ Браузер не запущен")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    logger.info("🚀 Бот с ВСЕМИ командами Pydoll запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()