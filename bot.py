import asyncio
import logging
import os
import json
import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.constants import Key, PageLoadState  # MouseButton удален

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
    def __init__(self):
        self.browser = None
        self.tab = None
        self.is_running = False
        
    async def start(self):
        if self.is_running:
            return self
            
        options = ChromiumOptions()
        options.binary_location = CHROME_PATH
        options.headless = True
        options.start_timeout = 30
        options.page_load_state = PageLoadState.INTERACTIVE
        
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--window-size=1920,1080')
        
        self.browser = Chrome(options=options)
        await self.browser.start()
        self.tab = await self.browser.get_tab()
        self.is_running = True
        
        logger.info("✅ Браузер запущен")
        return self
    
    async def execute(self, action: str, params: dict = None):
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
            
            # === ПОИСК ===
            "find": self._find,
            "find_all": self._find_all,
            
            # === ВЗАИМОДЕЙСТВИЕ ===
            "click": self._click,
            "click_js": self._click_js,
            "type": self._type,
            "type_human": self._type_human,
            "scroll": self._scroll,
            "scroll_to": self._scroll_to,
            "screenshot": self._screenshot,
            "get_text": self._get_text,
            "get_attribute": self._get_attribute,
            
            # === КЛАВИАТУРА ===
            "press_key": self._press_key,
            "press_enter": self._press_enter,
            "press_tab": self._press_tab,
            
            # === МЫШЬ ===
            "mouse_move": self._mouse_move,
            "mouse_click": self._mouse_click,
            
            # === ВКЛАДКИ ===
            "new_tab": self._new_tab,
            "switch_tab": self._switch_tab,
            "close_tab": self._close_tab,
            
            # === IFRAME ===
            "switch_iframe": self._switch_iframe,
            "exit_iframe": self._exit_iframe,
            
            # === JAVASCRIPT ===
            "execute_script": self._execute_script,
            
            # === ОЖИДАНИЕ ===
            "wait": self._wait,
            "wait_for": self._wait_for,
            
            # === КУКИ ===
            "get_cookies": self._get_cookies,
            "set_cookies": self._set_cookies,
            "delete_cookies": self._delete_cookies,
            
            # === STORAGE ===
            "get_local_storage": self._get_local_storage,
            "set_local_storage": self._set_local_storage,
            "clear_local_storage": self._clear_local_storage,
            
            # === ФОРМЫ ===
            "submit_form": self._submit_form,
            "clear_field": self._clear_field,
            
            # === СКРОЛЛ К ЭЛЕМЕНТУ ===
            "scroll_to_element": self._scroll_to_element
        }
        
        if action not in actions:
            raise ValueError(f"Неизвестное действие: {action}")
        
        return await actions[action](**params)
    
    # --- НАВИГАЦИЯ ---
    
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
    
    # --- ПОИСК ---
    
    async def _find(self, selector: str):
        element = await self.tab.find(selector)
        if element:
            text = await element.text
            return f"🔍 Найден: {text[:100]}"
        return f"❌ Элемент {selector} не найден"
    
    async def _find_all(self, selector: str):
        elements = await self.tab.find_all(selector)
        return f"🔍 Найдено {len(elements)} элементов"
    
    # --- ВЗАИМОДЕЙСТВИЕ ---
    
    async def _click(self, selector: str):
        element = await self.tab.find(selector)
        if element:
            await element.click(humanize=True)
            return f"✅ Кликнул по {selector}"
        return f"❌ Элемент {selector} не найден"
    
    async def _click_js(self, selector: str):
        element = await self.tab.find(selector)
        if element:
            await element.click_using_js()
            return f"✅ Кликнул (JS) по {selector}"
        return f"❌ Элемент {selector} не найден"
    
    async def _type(self, selector: str, text: str):
        element = await self.tab.find(selector)
        if element:
            await element.type_text(text)
            return f"✅ Ввел '{text}' в {selector}"
        return f"❌ Элемент {selector} не найден"
    
    async def _type_human(self, selector: str, text: str):
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
        
        # Получаем текст всей страницы
        elements = await self.tab.find_all("body *")
        texts = []
        for el in elements[:10]:
            text = await el.text
            if text.strip():
                texts.append(text.strip())
        return "\n".join(texts)[:500] if texts else "Текст не найден"
    
    async def _get_attribute(self, selector: str, attribute: str):
        element = await self.tab.find(selector)
        if element:
            value = await element.get_attribute(attribute)
            return f"📋 {attribute}: {value}"
        return f"❌ Элемент {selector} не найден"
    
    # --- КЛАВИАТУРА ---
    
    async def _press_key(self, key: str):
        await self.tab.keyboard.press(getattr(Key, key.upper(), Key.ENTER))
        return f"⌨️ Нажал {key}"
    
    async def _press_enter(self):
        await self.tab.keyboard.press(Key.ENTER)
        return "⌨️ Нажал Enter"
    
    async def _press_tab(self):
        await self.tab.keyboard.press(Key.TAB)
        return "⌨️ Нажал Tab"
    
    # --- МЫШЬ ---
    
    async def _mouse_move(self, x: int, y: int):
        await self.tab.mouse.move(x, y, humanize=True)
        return f"🖱️ Переместил мышь на ({x}, {y})"
    
    async def _mouse_click(self, x: int, y: int):
        await self.tab.mouse.click(x, y, humanize=True)
        return f"🖱️ Кликнул по ({x}, {y})"
    
    # --- ВКЛАДКИ ---
    
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
    
    # --- IFRAME ---
    
    async def _switch_iframe(self, selector: str):
        element = await self.tab.find(selector)
        if element:
            self.tab = await self.tab.get_frame(element)
            return "✅ Переключился в iframe"
        return f"❌ iframe {selector} не найден"
    
    async def _exit_iframe(self):
        self.tab = await self.tab.exit_frame()
        return "✅ Вышел из iframe"
    
    # --- JAVASCRIPT ---
    
    async def _execute_script(self, script: str):
        result = await self.tab.execute_script(script)
        return f"✅ JS: {str(result)[:200]}"
    
    # --- ОЖИДАНИЕ ---
    
    async def _wait(self, seconds: int = 2):
        await asyncio.sleep(seconds)
        return f"⏳ Подождал {seconds} сек"
    
    async def _wait_for(self, selector: str, timeout: int = 10):
        element = await self.tab.wait_for(selector, timeout=timeout)
        if element:
            return f"✅ Элемент {selector} появился"
        return f"❌ Элемент {selector} не появился"
    
    # --- КУКИ ---
    
    async def _get_cookies(self):
        cookies = await self.tab.cookies
        return f"🍪 Куки: {json.dumps(cookies, indent=2)[:500]}"
    
    async def _set_cookies(self, cookies: list):
        await self.tab.set_cookies(cookies)
        return "✅ Куки установлены"
    
    async def _delete_cookies(self):
        await self.tab.delete_all_cookies()
        return "🗑️ Куки удалены"
    
    # --- STORAGE ---
    
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
    
    # --- ФОРМЫ ---
    
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
    
    # --- СКРОЛЛ К ЭЛЕМЕНТУ ---
    
    async def _scroll_to_element(self, selector: str):
        element = await self.tab.find(selector)
        if element:
            await element.scroll_to()
            return f"✅ Прокрутил к {selector}"
        return f"❌ Элемент {selector} не найден"
    
    async def close(self):
        if self.browser and self.is_running:
            await self.browser.close()
            self.is_running = False
            logger.info("✅ Браузер закрыт")


# === AGNES AI ===

async def ask_agnes(prompt: str):
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
    prompt = f"""
    Команда: "{text}"
    
    Доступные действия:
    go_to, back, forward, refresh, get_title, get_url, get_html
    find, find_all
    click, click_js, type, type_human, scroll, scroll_to, screenshot, get_text, get_attribute
    press_key, press_enter, press_tab
    mouse_move, mouse_click
    new_tab, switch_tab, close_tab
    switch_iframe, exit_iframe
    execute_script
    wait, wait_for
    get_cookies, set_cookies, delete_cookies
    get_local_storage, set_local_storage, clear_local_storage
    submit_form, clear_field
    scroll_to_element
    
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
                
                if action == "screenshot" and result:
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
        "🤖 **AI-агент Pydoll**\n\n"
        "📝 **Примеры команд:**\n"
        "• Открой google.com\n"
        "• Сделай скриншот\n"
        "• Найди кнопку и кликни\n"
        "• Введи Python в поиск\n"
        "• Прокрути вниз\n"
        "• Нажми Enter\n\n"
        "💡 Просто напиши, что нужно сделать!",
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
    
    logger.info("🚀 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()