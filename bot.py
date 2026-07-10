#!/usr/bin/env python3
"""
Telegram Bot с интерактивным окном просмотра браузера
Версия: 6.0 - Live View с активным диалогом
"""

import asyncio
import logging
import os
import base64
import json
import traceback
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.constants import Key
from pydoll.exceptions import ElementNotFound, WaitElementTimeout, NetworkError

# ============================================================
# 1. НАСТРОЙКА
# ============================================================

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
if not AGNES_API_KEY:
    raise ValueError("AGNES_API_KEY не установлен!")

CHROME_PATH = os.environ.get("CHROME_PATH", "/usr/bin/google-chrome")
ADMIN_IDS = [int(id) for id in os.environ.get("ADMIN_IDS", "").split(",") if id]

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# ============================================================
# 2. УПРАВЛЕНИЕ БРАУЗЕРОМ
# ============================================================

@dataclass
class BrowserSession:
    browser: Optional[Chrome] = None
    tab: Optional[Any] = None
    is_active: bool = False
    current_url: str = ""
    page_title: str = ""
    comments: List[str] = field(default_factory=list)
    last_screenshot: Optional[str] = None
    waiting_for_response: bool = False
    pending_question: str = ""
    context_variables: Dict[str, Any] = field(default_factory=dict)

class SessionManager:
    def __init__(self):
        self.sessions: Dict[int, BrowserSession] = {}
        self._browser: Optional[Chrome] = None
        self._lock = asyncio.Lock()

    async def _get_or_create_browser(self) -> Chrome:
        if self._browser is None:
            options = ChromiumOptions()
            options.binary_location = CHROME_PATH
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--headless=new')
            options.start_timeout = 30

            self._browser = Chrome(options=options)
            await self._browser.start()
            logger.info("🌐 Браузер запущен")
        return self._browser

    async def get_session(self, user_id: int) -> BrowserSession:
        async with self._lock:
            if user_id not in self.sessions:
                session = BrowserSession()
                self.sessions[user_id] = session
                logger.info(f"🆕 Сессия для {user_id}")
            
            session = self.sessions[user_id]
            
            if not session.tab:
                browser = await self._get_or_create_browser()
                session.tab = await browser.new_tab()
                session.is_active = True
                session.comments = ["🟢 Браузер готов", "💡 Напиши что нужно сделать"]
            
            return session

    async def close_session(self, user_id: int):
        async with self._lock:
            if user_id in self.sessions:
                session = self.sessions[user_id]
                if session.tab:
                    try:
                        await session.tab.close()
                    except:
                        pass
                del self.sessions[user_id]
                logger.info(f"❌ Сессия {user_id} закрыта")

    async def close_all(self):
        for user_id in list(self.sessions.keys()):
            await self.close_session(user_id)
        if self._browser:
            try:
                await self._browser.stop()
            except:
                pass
            self._browser = None

session_manager = SessionManager()

# ============================================================
# 3. AGNES AI КЛИЕНТ
# ============================================================

agnes_client = None

def init_agnes():
    global agnes_client
    from openai import OpenAI
    agnes_client = OpenAI(
        api_key=AGNES_API_KEY,
        base_url="https://apihub.agnes-ai.com/v1",
    )
    logger.info("✅ Agnes AI клиент инициализирован")
    return agnes_client

# ============================================================
# 4. ИНТЕРАКТИВНОЕ ОКНО
# ============================================================

class LiveView:
    """Управление интерактивным окном"""
    
    @staticmethod
    async def send_or_update(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        screenshot: Optional[bytes] = None,
        comments: Optional[List[str]] = None,
        waiting_for_response: bool = False
    ):
        """Отправляет или обновляет окно"""
        
        session = await session_manager.get_session(user_id)
        
        if comments is not None:
            session.comments = comments
        elif screenshot:
            pass
        
        # Формируем caption
        caption = "🌐 **Управление браузером**\n"
        caption += f"🔗 URL: `{session.current_url or 'не загружен'}`\n"
        caption += f"📄 Заголовок: {session.page_title or 'не загружен'}\n"
        caption += "─" * 25 + "\n"
        caption += "💬 **Комментарии:**\n"
        
        # Последние 10 комментариев
        for comment in session.comments[-10:]:
            caption += f"  • {comment}\n"
        
        if waiting_for_response:
            caption += "\n❓ **Ожидаю ответа...**"
        
        # Кнопки
        keyboard = [
            [
                InlineKeyboardButton("🔄 Обновить", callback_data="view_refresh"),
                InlineKeyboardButton("📸 Скриншот", callback_data="view_screenshot"),
            ],
            [
                InlineKeyboardButton("⬅️ Назад", callback_data="view_back"),
                InlineKeyboardButton("⬆️ Вверх", callback_data="view_up"),
                InlineKeyboardButton("⬇️ Вниз", callback_data="view_down"),
            ],
            [
                InlineKeyboardButton("🔍 Найти", callback_data="view_find"),
                InlineKeyboardButton("⌨️ Ввод", callback_data="view_type"),
            ],
            [
                InlineKeyboardButton("⏹️ Закрыть", callback_data="view_close"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Если есть скриншот
        if screenshot:
            if context.user_data.get('view_message_id'):
                try:
                    await context.bot.edit_message_media(
                        chat_id=update.effective_chat.id,
                        message_id=context.user_data['view_message_id'],
                        media=InputMediaPhoto(
                            media=screenshot,
                            caption=caption,
                            parse_mode='Markdown'
                        ),
                        reply_markup=reply_markup
                    )
                    return
                except Exception as e:
                    logger.warning(f"Не удалось обновить медиа: {e}")
            
            # Отправляем новое
            if update.message:
                msg = await update.message.reply_photo(
                    photo=screenshot,
                    caption=caption,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            else:
                msg = await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=screenshot,
                    caption=caption,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            context.user_data['view_message_id'] = msg.message_id
        else:
            # Если скриншота нет, отправляем текст
            if context.user_data.get('view_message_id'):
                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=context.user_data['view_message_id'],
                        text=caption,
                        parse_mode='Markdown',
                        reply_markup=reply_markup
                    )
                    return
                except:
                    pass
            
            if update.message:
                msg = await update.message.reply_text(
                    text=caption,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            else:
                msg = await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=caption,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            context.user_data['view_message_id'] = msg.message_id

# ============================================================
# 5. ИНСТРУМЕНТЫ ДЛЯ AGNES AI
# ============================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "go_to_url",
            "description": "Переходит на указанный URL",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "type_into_search",
            "description": "Находит поле поиска и вводит текст",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "click_element",
            "description": "Кликает по элементу",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Делает скриншот страницы",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_down",
            "description": "Прокручивает страницу вниз",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_up",
            "description": "Прокручивает страницу вверх",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "go_back",
            "description": "Возвращает на предыдущую страницу",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_page_title",
            "description": "Получает заголовок страницы",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_javascript",
            "description": "Выполняет JavaScript код",
            "parameters": {
                "type": "object",
                "properties": {"script": {"type": "string"}},
                "required": ["script"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "Задаёт уточняющий вопрос пользователю",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["question"]
            }
        }
    }
]

# ============================================================
# 6. ИСПОЛНЕНИЕ ИНСТРУМЕНТОВ
# ============================================================

async def execute_tool(tool_name: str, arguments: Dict, user_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Dict:
    """Выполняет инструмент и обновляет окно"""
    session = await session_manager.get_session(user_id)
    tab = session.tab
    
    if not tab:
        return {"success": False, "error": "Браузер не открыт"}
    
    try:
        result = {"success": False}
        
        if tool_name == "go_to_url":
            url = arguments.get("url", "")
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            session.comments.append(f"🔗 Перехожу на {url}...")
            await tab.go_to(url)
            session.current_url = await tab.current_url
            session.page_title = await tab.title
            session.comments.append(f"✅ На {session.current_url}")
            result = {"success": True, "url": session.current_url, "title": session.page_title}
        
        elif tool_name == "type_into_search":
            text = arguments.get("text", "")
            session.comments.append(f"⌨️ Ищу поле для '{text}'...")
            
            selectors = [
                'input[type="search"]',
                'input[name="q"]',
                'input[name="search_query"]',
                'input[name="search"]',
                'input[placeholder*="search" i]',
                'input[placeholder*="поиск" i]',
            ]
            
            found = False
            for selector in selectors:
                try:
                    element = await tab.query(selector)
                    if element:
                        await element.clear()
                        await element.type_text(text, humanize=True)
                        await tab.keyboard.press(Key.ENTER)
                        session.comments.append(f"✅ Ввёл '{text}' и нажал Enter")
                        found = True
                        break
                except:
                    continue
            
            if not found:
                session.comments.append("❌ Не нашёл поле поиска")
                return {"success": False, "error": "Поле поиска не найдено"}
            
            result = {"success": True, "text": text}
        
        elif tool_name == "click_element":
            selector = arguments.get("selector", "")
            session.comments.append(f"🖱️ Кликаю {selector}...")
            element = await tab.query(selector)
            await element.click(humanize=True)
            session.comments.append("✅ Кликнул")
            result = {"success": True}
        
        elif tool_name == "take_screenshot":
            session.comments.append("📸 Делаю скриншот...")
            screenshot = await tab.take_screenshot(beyond_viewport=False, as_base64=True)
            session.last_screenshot = screenshot
            session.comments.append("✅ Скриншот готов")
            result = {"success": True, "screenshot": screenshot}
        
        elif tool_name == "scroll_down":
            session.comments.append("⬇️ Прокручиваю вниз...")
            await tab.execute_script("window.scrollBy(0, 300)")
            session.comments.append("✅ Прокрутил")
            result = {"success": True}
        
        elif tool_name == "scroll_up":
            session.comments.append("⬆️ Прокручиваю вверх...")
            await tab.execute_script("window.scrollBy(0, -300)")
            session.comments.append("✅ Прокрутил")
            result = {"success": True}
        
        elif tool_name == "go_back":
            session.comments.append("⬅️ Назад...")
            await tab.go_back()
            session.comments.append("✅ Назад")
            result = {"success": True}
        
        elif tool_name == "get_page_title":
            title = await tab.title
            session.comments.append(f"📄 Заголовок: {title}")
            result = {"success": True, "title": title}
        
        elif tool_name == "execute_javascript":
            script = arguments.get("script", "")
            session.comments.append("⚡ Выполняю JS...")
            js_result = await tab.execute_script(script)
            session.comments.append("✅ JS выполнен")
            result = {"success": True, "result": str(js_result)[:200]}
        
        elif tool_name == "ask_user":
            question = arguments.get("question", "")
            options = arguments.get("options", [])
            
            session.waiting_for_response = True
            session.pending_question = question
            
            message = f"❓ {question}"
            if options:
                message += "\n\n📌 **Варианты:**\n" + "\n".join([f"  • {opt}" for opt in options])
            
            session.comments.append(f"💬 {message}")
            result = {"success": True, "message": message, "awaiting_response": True}
        
        # Обновляем URL и заголовок
        try:
            session.current_url = await tab.current_url
            session.page_title = await tab.title
        except:
            pass
        
        # Показываем результат
        screenshot_data = None
        if result.get("screenshot"):
            screenshot_data = base64.b64decode(result["screenshot"])
        else:
            try:
                screenshot = await tab.take_screenshot(beyond_viewport=False, as_base64=True)
                screenshot_data = base64.b64decode(screenshot)
            except:
                pass
        
        await LiveView.send_or_update(
            update, context, user_id,
            screenshot=screenshot_data,
            comments=session.comments,
            waiting_for_response=session.waiting_for_response
        )
        
        return result
        
    except Exception as e:
        session.comments.append(f"❌ Ошибка: {str(e)}")
        await LiveView.send_or_update(
            update, context, user_id,
            comments=session.comments
        )
        return {"success": False, "error": str(e)}

# ============================================================
# 7. ОБРАБОТКА ЧЕРЕЗ AGNES AI
# ============================================================

async def process_with_agnes(user_message: str, user_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Dict:
    """Обрабатывает запрос через Agnes AI с активным диалогом"""
    global agnes_client
    
    if agnes_client is None:
        init_agnes()
    
    session = await session_manager.get_session(user_id)
    
    # Если ждём ответ, отвечаем на вопрос
    if session.waiting_for_response:
        session.waiting_for_response = False
        session.comments.append(f"💬 Ответ: {user_message}")
        await LiveView.send_or_update(
            update, context, user_id,
            comments=session.comments
        )
        return {"type": "text", "content": f"✅ Получил ответ: {user_message}"}
    
    system_prompt = f"""
Ты — AI агент, управляющий браузером через Pydoll.

**Текущее состояние:**
- URL: {session.current_url or 'не загружен'}
- Заголовок: {session.page_title or 'не загружен'}
- Браузер: {'открыт' if session.is_active else 'закрыт'}

**Твоя задача — ВЕСТИ АКТИВНЫЙ ДИАЛОГ с пользователем:**

1. Если запрос неполный — задай уточняющий вопрос через ask_user
2. Предлагай варианты действий
3. Сообщай о прогрессе
4. После выполнения — спрашивай, что дальше

**Примеры:**
- Пользователь: "Найди видео" → Ты: "На каком сайте искать?"
- Пользователь: "Сделай скриншот" → Ты делаешь и говоришь "Готово! Что дальше?"
- Пользователь: "Открой сайт" → Ты: "Какой сайт открыть?"

**Инструменты:**
- go_to_url(url) — перейти на сайт
- type_into_search(text) — поиск
- click_element(selector) — клик
- take_screenshot() — скриншот
- scroll_down() / scroll_up() — прокрутка
- go_back() — назад
- get_page_title() — заголовок
- execute_javascript(script) — JS
- ask_user(question, options) — задать вопрос

**Важно:**
- Всегда комментируй свои действия
- Будь дружелюбным и понятным
- Если что-то пошло не так — объясни ошибку
"""
    
    try:
        response = agnes_client.chat.completions.create(
            model="agnes-2.0-flash",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            tools=TOOLS,
            tool_choice="auto"
        )
        
        message = response.choices[0].message
        
        if message.tool_calls:
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                
                logger.info(f"🔧 Вызов: {tool_name}")
                
                result = await execute_tool(tool_name, arguments, user_id, update, context)
                
                if tool_name == "take_screenshot" and result.get("success") and result.get("screenshot"):
                    return {"type": "screenshot", "data": result["screenshot"]}
                
                if result.get("awaiting_response"):
                    return {"type": "text", "content": result.get("message")}
                
                if not result.get("success"):
                    return {"type": "text", "content": f"❌ {result.get('error', 'Ошибка')}"}
            
            return {"type": "text", "content": "✅ Готово! Что дальше?"}
        else:
            return {"type": "text", "content": message.content or "✅ Готово!"}
            
    except Exception as e:
        session.comments.append(f"❌ Ошибка AI: {str(e)}")
        await LiveView.send_or_update(
            update, context, user_id,
            comments=session.comments
        )
        return {"type": "text", "content": f"❌ Ошибка: {str(e)}"}

# ============================================================
# 8. КОМАНДЫ
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие"""
    await update.message.reply_text(
        "🤖 **Бот с интерактивным окном**\n\n"
        "Я управляю браузером и показываю что делаю!\n\n"
        "📌 **Команды:**\n"
        "• `/open` — Открыть браузер\n"
        "• `/go <url>` — Перейти на сайт\n"
        "• `/type <текст>` — Ввести текст в поиск\n"
        "• `/close` — Закрыть браузер\n\n"
        "💬 Или просто напиши, что нужно сделать!",
        parse_mode='Markdown'
    )

async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открывает браузер и показывает окно"""
    user_id = update.effective_user.id
    
    await update.message.reply_text("🌐 Открываю браузер...")
    
    try:
        session = await session_manager.get_session(user_id)
        session.comments = ["🟢 Браузер открыт", "💡 Напиши что нужно сделать"]
        session.current_url = await session.tab.current_url
        session.page_title = await session.tab.title
        
        # Первый скриншот
        screenshot = await session.tab.take_screenshot(
            beyond_viewport=False,
            as_base64=True
        )
        screenshot_bytes = base64.b64decode(screenshot)
        session.last_screenshot = screenshot
        
        await LiveView.send_or_update(
            update, context, user_id,
            screenshot=screenshot_bytes,
            comments=session.comments
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def go_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переходит на URL"""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("❌ Укажите URL\nПример: /go https://youtube.com")
        return
    
    url = context.args[0]
    session = await session_manager.get_session(user_id)
    
    result = await execute_tool("go_to_url", {"url": url}, user_id, update, context)
    
    if not result.get("success"):
        await update.message.reply_text(f"❌ {result.get('error', 'Ошибка')}")

async def type_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вводит текст в поиск"""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("❌ Укажите текст для поиска")
        return
    
    text = " ".join(context.args)
    
    result = await execute_tool("type_into_search", {"text": text}, user_id, update, context)
    
    if not result.get("success"):
        await update.message.reply_text(f"❌ {result.get('error', 'Ошибка')}")

async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрывает браузер"""
    user_id = update.effective_user.id
    
    await session_manager.close_session(user_id)
    context.user_data.pop('view_message_id', None)
    
    await update.message.reply_text("🔒 Браузер закрыт")

async def view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия кнопок"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    action = query.data.replace("view_", "")
    
    # Маппинг действий на инструменты
    action_map = {
        "refresh": ("refresh_page", {}),
        "screenshot": ("take_screenshot", {}),
        "back": ("go_back", {}),
        "up": ("scroll_up", {}),
        "down": ("scroll_down", {}),
    }
    
    if action in action_map:
        tool_name, args = action_map[action]
        await execute_tool(tool_name, args, user_id, update, context)
    
    elif action == "find":
        await query.edit_message_text(
            "🔍 Напиши текст для поиска через команду:\n"
            "`/type <текст>`",
            parse_mode='Markdown'
        )
    
    elif action == "type":
        await query.edit_message_text(
            "⌨️ Напиши текст для ввода через команду:\n"
            "`/type <текст>`",
            parse_mode='Markdown'
        )
    
    elif action == "close":
        await session_manager.close_session(user_id)
        context.user_data.pop('view_message_id', None)
        await query.edit_message_text("🔒 Браузер закрыт")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения"""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    if user_message.startswith('/'):
        return
    
    # Проверяем, открыт ли браузер
    session = await session_manager.get_session(user_id)
    if not session.tab:
        await update.message.reply_text("❌ Сначала открой браузер: /open")
        return
    
    await update.message.reply_text("🤔 Думаю...")
    
    try:
        result = await process_with_agnes(user_message, user_id, update, context)
        
        if result["type"] == "screenshot":
            try:
                screenshot_bytes = base64.b64decode(result["data"])
                
                # Сжимаем если слишком большое
                if len(screenshot_bytes) > 10 * 1024 * 1024:
                    try:
                        from PIL import Image
                        import io
                        image = Image.open(io.BytesIO(screenshot_bytes))
                        if image.width > 1280:
                            ratio = 1280 / image.width
                            new_size = (1280, int(image.height * ratio))
                            image = image.resize(new_size, Image.Resampling.LANCZOS)
                            buffer = io.BytesIO()
                            image.save(buffer, format='PNG', optimize=True)
                            screenshot_bytes = buffer.getvalue()
                    except:
                        pass
                
                await update.message.reply_photo(
                    screenshot_bytes,
                    caption="📸 Скриншот"
                )
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка отправки скриншота: {str(e)}")
        else:
            await update.message.reply_text(result["content"])
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    error = context.error
    logger.error(f"Ошибка: {error}\n{traceback.format_exc()}")

# ============================================================
# 9. ЗАПУСК
# ============================================================

async def main():
    try:
        init_agnes()
        
        application = Application.builder().token(TOKEN).build()
        
        # Команды
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("open", open_command))
        application.add_handler(CommandHandler("go", go_command))
        application.add_handler(CommandHandler("type", type_command))
        application.add_handler(CommandHandler("close", close_command))
        
        # Callback для кнопок
        application.add_handler(CallbackQueryHandler(view_callback, pattern="^view_"))
        
        # Обработчики
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_error_handler(error_handler)
        
        logger.info("=" * 60)
        logger.info("🚀 Бот с интерактивным окном запущен!")
        logger.info("📌 Команды: /open, /go, /type, /close")
        logger.info("💬 Пиши что нужно сделать в чат!")
        logger.info("=" * 60)
        
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
    finally:
        await session_manager.close_all()

if __name__ == "__main__":
    asyncio.run(main())