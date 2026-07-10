#!/usr/bin/env python3
"""
Telegram Bot с интерактивным окном браузера
Версия: 8.0 - Одно окно, без спама
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
from pydoll.exceptions import ElementNotFound, WaitElementTimeout

# ============================================================
# НАСТРОЙКА
# ============================================================

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
if not AGNES_API_KEY:
    raise ValueError("AGNES_API_KEY не установлен!")

CHROME_PATH = os.environ.get("CHROME_PATH", "/usr/bin/google-chrome")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# ============================================================
# УПРАВЛЕНИЕ БРАУЗЕРОМ
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
    waiting_for_input: bool = False
    pending_action: str = ""

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
                session.comments = ["🟢 Браузер готов"]
                session.current_url = await session.tab.current_url
                session.page_title = await session.tab.title
            
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
# AGNES AI КЛИЕНТ
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
# КЛАВИАТУРА
# ============================================================

def get_main_keyboard():
    """Главная клавиатура"""
    keyboard = [
        [
            InlineKeyboardButton("🌐 Сайты", callback_data="menu_sites"),
            InlineKeyboardButton("🔍 Поиск", callback_data="menu_search"),
            InlineKeyboardButton("📸 Скрин", callback_data="menu_screenshot"),
        ],
        [
            InlineKeyboardButton("⬆️", callback_data="menu_up"),
            InlineKeyboardButton("⬇️", callback_data="menu_down"),
            InlineKeyboardButton("🔄", callback_data="menu_refresh"),
            InlineKeyboardButton("⬅️", callback_data="menu_back"),
        ],
        [
            InlineKeyboardButton("⚡ JS", callback_data="menu_js"),
            InlineKeyboardButton("📊 Данные", callback_data="menu_data"),
            InlineKeyboardButton("🔒 Закрыть", callback_data="menu_close"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_sites_keyboard():
    """Клавиатура с сайтами"""
    keyboard = [
        [
            InlineKeyboardButton("🔴 YouTube", callback_data="site_youtube"),
            InlineKeyboardButton("🔵 Google", callback_data="site_google"),
        ],
        [
            InlineKeyboardButton("📘 GitHub", callback_data="site_github"),
            InlineKeyboardButton("🟦 Wikipedia", callback_data="site_wikipedia"),
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data="menu_main"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

# ============================================================
# ОБНОВЛЕНИЕ ОКНА
# ============================================================

async def update_window(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, force_new: bool = False):
    """Обновляет окно с браузером"""
    session = await session_manager.get_session(user_id)
    
    if not session.tab or not session.is_active:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🔒 Браузер закрыт. Используйте /open"
        )
        return
    
    # Получаем актуальные данные
    try:
        session.current_url = await session.tab.current_url
        session.page_title = await session.tab.title
    except:
        session.comments.append("⚠️ Ошибка получения данных")
    
    # Делаем скриншот
    screenshot_bytes = None
    try:
        screenshot = await session.tab.take_screenshot(
            beyond_viewport=False,
            as_base64=True
        )
        screenshot_bytes = base64.b64decode(screenshot)
        session.last_screenshot = screenshot
    except Exception as e:
        session.comments.append(f"❌ Ошибка скриншота: {str(e)}")
    
    # Формируем текст
    caption = "🌐 **Браузер**\n"
    caption += f"🔗 `{session.current_url or 'не загружен'}`\n"
    caption += f"📄 {session.page_title or 'не загружен'}\n"
    caption += "─" * 20 + "\n"
    
    # Комментарии (последние 5)
    for comment in session.comments[-5:]:
        caption += f"💬 {comment}\n"
    
    # Если ждём ввод
    if session.waiting_for_input:
        caption += f"\n✏️ {session.pending_action}"
    
    # Клавиатура
    reply_markup = get_main_keyboard()
    
    # Отправляем или обновляем
    msg_id = context.user_data.get('view_message_id')
    
    if msg_id and not force_new:
        try:
            if screenshot_bytes:
                await context.bot.edit_message_media(
                    chat_id=update.effective_chat.id,
                    message_id=msg_id,
                    media=InputMediaPhoto(
                        media=screenshot_bytes,
                        caption=caption,
                        parse_mode='Markdown'
                    ),
                    reply_markup=reply_markup
                )
            else:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=msg_id,
                    text=caption,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            return
        except Exception as e:
            logger.warning(f"Не удалось обновить: {e}")
    
    # Отправляем новое
    if screenshot_bytes:
        msg = await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=screenshot_bytes,
            caption=caption,
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
# ВЫПОЛНЕНИЕ ДЕЙСТВИЙ
# ============================================================

async def execute_action(action: str, user_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = ""):
    """Выполняет действие и обновляет окно"""
    session = await session_manager.get_session(user_id)
    tab = session.tab
    
    if not tab:
        session.comments.append("❌ Браузер не открыт")
        await update_window(update, context, user_id)
        return
    
    try:
        if action == "go_to_url":
            if not text.startswith(('http://', 'https://')):
                text = 'https://' + text
            session.comments.append(f"🔗 Перехожу на {text}")
            await tab.go_to(text)
            session.current_url = await tab.current_url
            session.page_title = await tab.title
            session.comments.append("✅ Готово")
        
        elif action == "search":
            session.comments.append(f"🔍 Ищу '{text}'...")
            
            # Пробуем найти поле поиска
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
                        session.comments.append("✅ Готово")
                        found = True
                        break
                except:
                    continue
            
            if not found:
                session.comments.append("❌ Не нашёл поле поиска")
        
        elif action == "screenshot":
            session.comments.append("📸 Делаю скриншот...")
            screenshot = await tab.take_screenshot(beyond_viewport=False, as_base64=True)
            session.last_screenshot = screenshot
            session.comments.append("✅ Готово")
        
        elif action == "refresh":
            session.comments.append("🔄 Обновляю...")
            await tab.refresh()
            session.comments.append("✅ Готово")
        
        elif action == "back":
            session.comments.append("⬅️ Назад...")
            await tab.go_back()
            session.comments.append("✅ Готово")
        
        elif action == "up":
            session.comments.append("⬆️ Вверх...")
            await tab.execute_script("window.scrollBy(0, -300)")
            session.comments.append("✅ Готово")
        
        elif action == "down":
            session.comments.append("⬇️ Вниз...")
            await tab.execute_script("window.scrollBy(0, 300)")
            session.comments.append("✅ Готово")
        
        elif action == "js":
            session.comments.append("⚡ Выполняю JS...")
            result = await tab.execute_script(text)
            session.comments.append(f"✅ Результат: {str(result)[:100]}")
        
        elif action == "data":
            session.comments.append("📊 Собираю данные...")
            result = await tab.execute_script(f"""
                const elements = document.querySelectorAll('{text}');
                return Array.from(elements).map(el => el.innerText.trim()).slice(0, 10);
            """)
            if result:
                session.comments.append(f"📊 Найдено: {len(result)} элементов")
                for item in result[:3]:
                    session.comments.append(f"  • {item[:50]}")
            else:
                session.comments.append("❌ Ничего не найдено")
        
        elif action == "close":
            await session_manager.close_session(user_id)
            context.user_data.pop('view_message_id', None)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🔒 Браузер закрыт"
            )
            return
        
    except Exception as e:
        session.comments.append(f"❌ Ошибка: {str(e)}")
    
    # Обновляем окно
    await update_window(update, context, user_id)

# ============================================================
# ОБРАБОТКА AI
# ============================================================

async def process_with_ai(user_message: str, user_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает запрос через AI"""
    global agnes_client
    
    if agnes_client is None:
        init_agnes()
    
    session = await session_manager.get_session(user_id)
    
    # Если ждём ввод
    if session.waiting_for_input:
        session.waiting_for_input = False
        action = session.pending_action
        
        if action == "search":
            await execute_action("search", user_id, update, context, user_message)
        elif action == "go_to_url":
            await execute_action("go_to_url", user_id, update, context, user_message)
        elif action == "js":
            await execute_action("js", user_id, update, context, user_message)
        elif action == "data":
            await execute_action("data", user_id, update, context, user_message)
        return
    
    # AI обработка
    system_prompt = f"""
Ты — AI агент, управляющий браузером.

Текущее состояние:
- URL: {session.current_url or 'не загружен'}
- Браузер: {'открыт' if session.is_active else 'закрыт'}

Доступные действия:
- go_to_url: перейти на сайт
- search: найти на странице
- screenshot: сделать скриншот
- refresh: обновить
- back: назад
- up/down: прокрутка
- js: выполнить JS
- data: собрать данные

Если запрос неполный — задай уточняющий вопрос.
Если понятно — выполни действие.
Отвечай кратко.
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
                
                if tool_name == "go_to_url":
                    await execute_action("go_to_url", user_id, update, context, arguments.get("url", ""))
                elif tool_name == "search":
                    await execute_action("search", user_id, update, context, arguments.get("text", ""))
                elif tool_name == "screenshot":
                    await execute_action("screenshot", user_id, update, context)
                elif tool_name == "refresh":
                    await execute_action("refresh", user_id, update, context)
                elif tool_name == "back":
                    await execute_action("back", user_id, update, context)
                elif tool_name == "scroll":
                    direction = arguments.get("direction", "down")
                    if direction == "up":
                        await execute_action("up", user_id, update, context)
                    else:
                        await execute_action("down", user_id, update, context)
                elif tool_name == "ask":
                    session.waiting_for_input = True
                    session.pending_action = arguments.get("action", "search")
                    session.comments.append(f"❓ {arguments.get('question', '')}")
                    await update_window(update, context, user_id)
        else:
            session.comments.append(f"💬 {message.content}")
            await update_window(update, context, user_id)
            
    except Exception as e:
        session.comments.append(f"❌ Ошибка AI: {str(e)}")
        await update_window(update, context, user_id)

# ============================================================
# ИНСТРУМЕНТЫ ДЛЯ AI
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
            "name": "search",
            "description": "Находит на странице и вводит текст в поиск",
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
            "name": "screenshot",
            "description": "Делает скриншот страницы",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "refresh",
            "description": "Обновляет страницу",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "back",
            "description": "Возвращает на предыдущую страницу",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Прокручивает страницу",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"]}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ask",
            "description": "Задаёт уточняющий вопрос пользователю",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "action": {"type": "string", "enum": ["search", "go_to_url", "js", "data"]}
                },
                "required": ["question"]
            }
        }
    }
]

# ============================================================
# КОМАНДЫ
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Бот с браузером**\n\n"
        "Просто напиши что нужно сделать:\n"
        "• `Перейди на youtube.com`\n"
        "• `Найди котиков`\n"
        "• `Сделай скриншот`\n"
        "• `Прокрути вниз`\n\n"
        "📌 **Команды:**\n"
        "/open — Открыть браузер\n"
        "/close — Закрыть браузер",
        parse_mode='Markdown'
    )

async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = await session_manager.get_session(user_id)
    session.comments = ["🟢 Браузер открыт", "💬 Напиши что нужно сделать"]
    await update_window(update, context, user_id)

async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await session_manager.close_session(user_id)
    context.user_data.pop('view_message_id', None)
    await update.message.reply_text("🔒 Браузер закрыт")

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия кнопок"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    session = await session_manager.get_session(user_id)
    
    if data == "menu_main":
        await update_window(update, context, user_id)
    
    elif data == "menu_sites":
        await context.bot.edit_message_reply_markup(
            chat_id=update.effective_chat.id,
            message_id=query.message.message_id,
            reply_markup=get_sites_keyboard()
        )
    
    elif data == "menu_search":
        session.waiting_for_input = True
        session.pending_action = "search"
        session.comments.append("✏️ Напиши текст для поиска")
        await update_window(update, context, user_id)
    
    elif data == "menu_screenshot":
        await execute_action("screenshot", user_id, update, context)
    
    elif data == "menu_up":
        await execute_action("up", user_id, update, context)
    
    elif data == "menu_down":
        await execute_action("down", user_id, update, context)
    
    elif data == "menu_refresh":
        await execute_action("refresh", user_id, update, context)
    
    elif data == "menu_back":
        await execute_action("back", user_id, update, context)
    
    elif data == "menu_js":
        session.waiting_for_input = True
        session.pending_action = "js"
        session.comments.append("✏️ Напиши JavaScript код")
        await update_window(update, context, user_id)
    
    elif data == "menu_data":
        session.waiting_for_input = True
        session.pending_action = "data"
        session.comments.append("✏️ Напиши CSS селектор для данных")
        await update_window(update, context, user_id)
    
    elif data == "menu_close":
        await session_manager.close_session(user_id)
        context.user_data.pop('view_message_id', None)
        await query.edit_message_text("🔒 Браузер закрыт")
    
    elif data.startswith("site_"):
        site = data.replace("site_", "")
        sites = {
            "youtube": "youtube.com",
            "google": "google.com",
            "github": "github.com",
            "wikipedia": "wikipedia.org",
        }
        if site in sites:
            await execute_action("go_to_url", user_id, update, context, sites[site])
            await update_window(update, context, user_id)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if text.startswith('/'):
        return
    
    session = await session_manager.get_session(user_id)
    
    if not session.tab:
        await update.message.reply_text("❌ Сначала открой браузер: /open")
        return
    
    # Если ждём ввод
    if session.waiting_for_input:
        action = session.pending_action
        session.waiting_for_input = False
        
        if action == "search":
            await execute_action("search", user_id, update, context, text)
        elif action == "go_to_url":
            await execute_action("go_to_url", user_id, update, context, text)
        elif action == "js":
            await execute_action("js", user_id, update, context, text)
        elif action == "data":
            await execute_action("data", user_id, update, context, text)
        return
    
    # Отправляем в AI
    await process_with_ai(text, user_id, update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}\n{traceback.format_exc()}")

# ============================================================
# ЗАПУСК
# ============================================================

async def main():
    try:
        init_agnes()
        
        application = Application.builder().token(TOKEN).build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("open", open_command))
        application.add_handler(CommandHandler("close", close_command))
        
        application.add_handler(CallbackQueryHandler(menu_callback, pattern="^(menu_|site_)"))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_error_handler(error_handler)
        
        logger.info("=" * 60)
        logger.info("🚀 Бот с интерактивным окном запущен!")
        logger.info("📌 Команды: /open, /close")
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