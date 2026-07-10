#!/usr/bin/env python3
"""
Telegram Bot с полным контролем браузера через Pydoll
Версия: 9.0 - ВСЕ ВОЗМОЖНОСТИ
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
# ПРОДВИНУТЫЕ ИМПОРТЫ PYDOLL
# ============================================================
try:
    from pydoll.extractor import ExtractionModel, Field
    EXTRACTION_AVAILABLE = True
except ImportError:
    EXTRACTION_AVAILABLE = False

try:
    from pydoll.protocol.fetch.events import FetchEvent
    from pydoll.protocol.network.types import ErrorReason
    FETCH_AVAILABLE = True
except ImportError:
    FETCH_AVAILABLE = False

try:
    from pydoll.utils import SOCKS5Forwarder
    SOCKS5_AVAILABLE = True
except ImportError:
    SOCKS5_AVAILABLE = False

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
# КУКИ ДЛЯ X.COM
# ============================================================

TWITTER_COOKIES = [
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "__cuid",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "55d2d7c5-4888-430a-b024-dd785da46ef4"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "lang",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "ru"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "dnt",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "1"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "guest_id",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "v1%3A178267838599411411"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "guest_id_marketing",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "v1%3A178267838599411411"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "guest_id_ads",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "v1%3A178267838599411411"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "personalization_id",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "\"v1_DKrxLZAC902dMFdd1QrVYg==\""
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "twid",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "u%3D2067347503503052800"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "auth_token",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "ct0",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb"
    }
]

# ============================================================
# УПРАВЛЕНИЕ БРАУЗЕРОМ
# ============================================================

@dataclass
class BrowserSession:
    browser: Optional[Chrome] = None
    context_id: Optional[str] = None
    tab: Optional[Any] = None
    tabs: List[Any] = field(default_factory=list)
    current_tab_index: int = 0
    is_active: bool = False
    current_url: str = ""
    page_title: str = ""
    comments: List[str] = field(default_factory=list)
    last_screenshot: Optional[str] = None
    waiting_for_input: bool = False
    pending_action: str = ""
    cookies_set: bool = False
    cookies_domain: str = ""
    har_capture: Optional[Any] = None
    shadow_roots: List[Any] = field(default_factory=list)

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

    async def _set_cookies_browser_level(self, browser, cookies: List[Dict], context_id: str = None) -> bool:
        try:
            domain = cookies[0].get("domain", "").lstrip('.')
            if not domain:
                return False
            
            logger.info(f"🍪 Устанавливаю {len(cookies)} кук")
            
            formatted_cookies = []
            for cookie in cookies:
                formatted_cookies.append({
                    "name": cookie["name"],
                    "value": cookie["value"],
                    "domain": cookie["domain"],
                    "path": cookie["path"],
                    "secure": cookie.get("secure", False),
                    "httpOnly": cookie.get("httpOnly", False),
                })
            
            await browser.set_cookies(
                cookies=formatted_cookies,
                browser_context_id=context_id
            )
            
            logger.info(f"✅ Установлено {len(formatted_cookies)} кук")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка установки кук: {e}")
            return False

    async def get_session(self, user_id: int) -> BrowserSession:
        async with self._lock:
            if user_id not in self.sessions:
                session = BrowserSession()
                self.sessions[user_id] = session
                logger.info(f"🆕 Сессия для {user_id}")
            
            session = self.sessions[user_id]
            
            if not session.tab:
                browser = await self._get_or_create_browser()
                
                try:
                    session.context_id = await browser.create_browser_context()
                    logger.info(f"🔒 Создан контекст {session.context_id}")
                except AttributeError:
                    session.context_id = None
                
                session.tab = await browser.new_tab(
                    browser_context_id=session.context_id
                ) if session.context_id else await browser.new_tab()
                session.tabs = [session.tab]
                session.is_active = True
                
                if not session.cookies_set:
                    try:
                        success = await self._set_cookies_browser_level(
                            browser=browser,
                            cookies=TWITTER_COOKIES,
                            context_id=session.context_id
                        )
                        if success:
                            session.cookies_set = True
                            session.cookies_domain = "x.com"
                            await session.tab.go_to("https://x.com")
                            await asyncio.sleep(2)
                            session.comments = [
                                "🟢 Браузер открыт",
                                "🍪 Куки установлены",
                                "✅ Готов к работе"
                            ]
                    except Exception as e:
                        session.comments = [f"🟢 Браузер открыт", f"❌ Ошибка: {str(e)}"]
                
                try:
                    session.current_url = await session.tab.current_url
                    session.page_title = await session.tab.title
                except:
                    pass
            
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
                if session.context_id and session.browser:
                    try:
                        await session.browser.close_browser_context(session.context_id)
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
    keyboard = [
        [
            InlineKeyboardButton("🔴 YouTube", callback_data="site_youtube"),
            InlineKeyboardButton("🔵 Google", callback_data="site_google"),
        ],
        [
            InlineKeyboardButton("📘 GitHub", callback_data="site_github"),
            InlineKeyboardButton("🐦 X/Twitter", callback_data="site_x"),
        ],
        [
            InlineKeyboardButton("🟦 Wikipedia", callback_data="site_wikipedia"),
            InlineKeyboardButton("🔙 Назад", callback_data="menu_main"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

# ============================================================
# ОБНОВЛЕНИЕ ОКНА
# ============================================================

async def update_window(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, force_new: bool = False):
    session = await session_manager.get_session(user_id)
    
    if not session.tab or not session.is_active:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🔒 Браузер закрыт. Используйте /open"
        )
        return
    
    try:
        session.current_url = await session.tab.current_url
        session.page_title = await session.tab.title
    except:
        session.comments.append("⚠️ Ошибка получения данных")
    
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
    
    caption = "🌐 Браузер\n"
    caption += f"URL: {session.current_url or 'не загружен'}\n"
    caption += f"Заголовок: {session.page_title or 'не загружен'}\n"
    caption += f"Вкладок: {len(session.tabs)}\n"
    caption += "─" * 20 + "\n"
    
    if session.cookies_set:
        caption += f"🍪 Куки {session.cookies_domain} установлены ✅\n"
    
    for comment in session.comments[-5:]:
        safe_comment = comment.replace('_', '\\_').replace('*', '\\*').replace('`', '\\`')
        caption += f"💬 {safe_comment}\n"
    
    if session.waiting_for_input:
        caption += f"\n✏️ {session.pending_action}"
    
    reply_markup = get_main_keyboard()
    msg_id = context.user_data.get('view_message_id')
    
    if msg_id and not force_new:
        try:
            current_msg = await context.bot.get_message(
                chat_id=update.effective_chat.id,
                message_id=msg_id
            )
            if current_msg.caption == caption and current_msg.reply_markup == reply_markup:
                return
        except:
            pass
    
    try:
        if msg_id and not force_new:
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
        else:
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
    except Exception as e:
        if "Message is not modified" in str(e):
            return
        logger.warning(f"Ошибка: {e}")
        clean_caption = caption.replace('**', '').replace('`', '').replace('_', '').replace('*', '')
        try:
            if msg_id and not force_new:
                if screenshot_bytes:
                    await context.bot.edit_message_media(
                        chat_id=update.effective_chat.id,
                        message_id=msg_id,
                        media=InputMediaPhoto(
                            media=screenshot_bytes,
                            caption=clean_caption,
                            parse_mode=None
                        ),
                        reply_markup=reply_markup
                    )
                else:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=msg_id,
                        text=clean_caption,
                        parse_mode=None,
                        reply_markup=reply_markup
                    )
            else:
                if screenshot_bytes:
                    msg = await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=screenshot_bytes,
                        caption=clean_caption,
                        parse_mode=None,
                        reply_markup=reply_markup
                    )
                else:
                    msg = await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=clean_caption,
                        parse_mode=None,
                        reply_markup=reply_markup
                    )
                context.user_data['view_message_id'] = msg.message_id
        except:
            pass

# ============================================================
# ВЫПОЛНЕНИЕ ДЕЙСТВИЙ - ВСЕ ВОЗМОЖНОСТИ
# ============================================================

async def execute_action(action: str, user_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = ""):
    session = await session_manager.get_session(user_id)
    tab = session.tab
    browser = session.browser
    
    if not tab:
        session.comments.append("❌ Браузер не открыт")
        await update_window(update, context, user_id)
        return
    
    try:
        # ============================================================
        # НАВИГАЦИЯ
        # ============================================================
        if action == "go_to_url":
            if not text.startswith(('http://', 'https://')):
                text = 'https://' + text
            session.comments.append(f"🔗 Перехожу на {text}")
            await tab.go_to(text)
            session.current_url = await tab.current_url
            session.page_title = await tab.title
            session.comments.append("✅ Готово")
        
        elif action == "go_back":
            session.comments.append("⬅️ Назад")
            await tab.go_back()
            session.comments.append("✅ Готово")
        
        elif action == "go_forward":
            session.comments.append("➡️ Вперёд")
            await tab.go_forward()
            session.comments.append("✅ Готово")
        
        elif action == "refresh":
            session.comments.append("🔄 Обновляю")
            await tab.refresh()
            session.comments.append("✅ Готово")
        
        elif action == "new_tab":
            session.comments.append("📑 Открываю новую вкладку")
            new_tab = await browser.new_tab()
            session.tabs.append(new_tab)
            session.tab = new_tab
            session.current_tab_index = len(session.tabs) - 1
            session.comments.append(f"✅ Вкладка {session.current_tab_index + 1}")
        
        elif action == "close_tab":
            if len(session.tabs) > 1:
                session.comments.append("❌ Закрываю вкладку")
                await session.tab.close()
                session.tabs.pop(session.current_tab_index)
                session.current_tab_index = min(session.current_tab_index, len(session.tabs) - 1)
                session.tab = session.tabs[session.current_tab_index]
                session.comments.append("✅ Закрыто")
            else:
                session.comments.append("⚠️ Нельзя закрыть последнюю вкладку")
        
        elif action == "switch_tab":
            try:
                index = int(text) - 1
                if 0 <= index < len(session.tabs):
                    session.current_tab_index = index
                    session.tab = session.tabs[index]
                    session.comments.append(f"✅ Переключился на вкладку {index + 1}")
                else:
                    session.comments.append(f"❌ Вкладка {text} не найдена")
            except:
                session.comments.append(f"❌ Неверный номер вкладки: {text}")
        
        # ============================================================
        # ПОИСК ЭЛЕМЕНТОВ
        # ============================================================
        elif action == "find_element":
            try:
                element = await tab.query(text)
                element_text = await element.text
                session.comments.append(f"✅ Найден элемент: {element_text[:100]}")
            except ElementNotFound:
                session.comments.append(f"❌ Элемент не найден: {text}")
        
        elif action == "find_element_by_xpath":
            try:
                element = await tab.query(text)
                element_text = await element.text
                session.comments.append(f"✅ Найден элемент по XPath: {element_text[:100]}")
            except:
                session.comments.append(f"❌ Элемент не найден по XPath: {text}")
        
        elif action == "find_element_by_text":
            try:
                elements = await tab.find(tag_name="*", text=text, find_all=True)
                if elements:
                    session.comments.append(f"✅ Найдено {len(elements)} элементов с текстом '{text}'")
                else:
                    session.comments.append(f"❌ Текст '{text}' не найден")
            except:
                session.comments.append(f"❌ Ошибка поиска текста: {text}")
        
        elif action == "find_all_elements":
            try:
                elements = await tab.find(tag_name=text, find_all=True) if text else await tab.find(tag_name="*", find_all=True)
                session.comments.append(f"✅ Найдено {len(elements)} элементов")
            except:
                session.comments.append(f"❌ Ошибка поиска элементов")
        
        # ============================================================
        # ВЗАИМОДЕЙСТВИЕ
        # ============================================================
        elif action == "click":
            try:
                element = await tab.query(text)
                await element.click()
                session.comments.append(f"🖱️ Кликнул по {text}")
            except:
                session.comments.append(f"❌ Не удалось кликнуть: {text}")
        
        elif action == "click_humanize":
            try:
                element = await tab.query(text)
                await element.click(humanize=True)
                session.comments.append(f"🖱️ Кликнул (humanize) по {text}")
            except:
                session.comments.append(f"❌ Не удалось кликнуть: {text}")
        
        elif action == "type_text":
            parts = text.split('|', 1)
            if len(parts) == 2:
                selector, value = parts[0].strip(), parts[1].strip()
                try:
                    element = await tab.query(selector)
                    await element.clear()
                    await element.type_text(value)
                    session.comments.append(f"⌨️ Ввёл текст в {selector}")
                except:
                    session.comments.append(f"❌ Не удалось ввести текст")
            else:
                session.comments.append("❌ Формат: selector|текст")
        
        elif action == "type_text_humanize":
            parts = text.split('|', 1)
            if len(parts) == 2:
                selector, value = parts[0].strip(), parts[1].strip()
                try:
                    element = await tab.query(selector)
                    await element.clear()
                    await element.type_text(value, humanize=True)
                    session.comments.append(f"⌨️ Ввёл текст (humanize) в {selector}")
                except:
                    session.comments.append(f"❌ Не удалось ввести текст")
            else:
                session.comments.append("❌ Формат: selector|текст")
        
        elif action == "clear":
            try:
                element = await tab.query(text)
                await element.clear()
                session.comments.append(f"🧹 Очистил {text}")
            except:
                session.comments.append(f"❌ Не удалось очистить: {text}")
        
        elif action == "get_text":
            try:
                element = await tab.query(text)
                element_text = await element.text
                session.comments.append(f"📄 Текст: {element_text[:200]}")
            except:
                session.comments.append(f"❌ Не удалось получить текст: {text}")
        
        elif action == "get_attribute":
            parts = text.split('|', 1)
            if len(parts) == 2:
                selector, attr = parts[0].strip(), parts[1].strip()
                try:
                    element = await tab.query(selector)
                    value = await element.get_attribute(attr)
                    session.comments.append(f"📄 {attr}: {value[:100]}")
                except:
                    session.comments.append(f"❌ Не удалось получить атрибут")
            else:
                session.comments.append("❌ Формат: selector|атрибут")
        
        elif action == "get_value":
            try:
                element = await tab.query(text)
                value = await element.value
                session.comments.append(f"📄 Значение: {value[:100]}")
            except:
                session.comments.append(f"❌ Не удалось получить значение: {text}")
        
        elif action == "is_visible":
            try:
                element = await tab.query(text)
                visible = await element.is_visible()
                session.comments.append(f"👁️ Видим: {visible}")
            except:
                session.comments.append(f"❌ Элемент не найден: {text}")
        
        elif action == "is_enabled":
            try:
                element = await tab.query(text)
                enabled = await element.is_interactable()
                session.comments.append(f"🔘 Доступен: {enabled}")
            except:
                session.comments.append(f"❌ Элемент не найден: {text}")
        
        # ============================================================
        # ПРОКРУТКА
        # ============================================================
        elif action == "scroll_up":
            amount = int(text) if text else 300
            await tab.execute_script(f"window.scrollBy(0, -{amount})")
            session.comments.append(f"⬆️ Вверх на {amount}")
        
        elif action == "scroll_down":
            amount = int(text) if text else 300
            await tab.execute_script(f"window.scrollBy(0, {amount})")
            session.comments.append(f"⬇️ Вниз на {amount}")
        
        elif action == "scroll_to_element":
            try:
                element = await tab.query(text)
                await tab.scroll.to_element(element, smooth=True)
                session.comments.append(f"📜 Прокрутил к {text}")
            except:
                session.comments.append(f"❌ Не удалось прокрутить к {text}")
        
        elif action == "scroll_to_top":
            await tab.execute_script("window.scrollTo(0, 0)")
            session.comments.append("⬆️ Вверх страницы")
        
        elif action == "scroll_to_bottom":
            await tab.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            session.comments.append("⬇️ Вниз страницы")
        
        # ============================================================
        # СКРИНШОТЫ
        # ============================================================
        elif action == "screenshot":
            screenshot = await tab.take_screenshot(beyond_viewport=False, as_base64=True)
            session.last_screenshot = screenshot
            session.comments.append("📸 Скриншот готов")
        
        elif action == "screenshot_full_page":
            screenshot = await tab.take_screenshot(beyond_viewport=True, as_base64=True)
            session.last_screenshot = screenshot
            session.comments.append("📸 Полный скриншот готов")
        
        elif action == "screenshot_element":
            try:
                element = await tab.query(text)
                screenshot = await element.take_screenshot(as_base64=True)
                session.last_screenshot = screenshot
                session.comments.append(f"📸 Скриншот элемента {text}")
            except:
                session.comments.append(f"❌ Не удалось сделать скриншот элемента: {text}")
        
        # ============================================================
        # ДАННЫЕ
        # ============================================================
        elif action == "get_page_title":
            title = await tab.title
            session.comments.append(f"📄 {title}")
        
        elif action == "get_current_url":
            url = await tab.current_url
            session.comments.append(f"🔗 {url}")
        
        elif action == "get_page_source":
            source = await tab.page_source
            session.comments.append(f"📄 HTML: {len(source)} символов")
        
        elif action == "get_cookies":
            cookies = await tab.get_cookies()
            session.comments.append(f"🍪 Кук: {len(cookies)}")
            for cookie in cookies[:3]:
                session.comments.append(f"  • {cookie.get('name')}: {cookie.get('value', '')[:20]}")
        
        elif action == "set_cookie":
            parts = text.split('|', 2)
            if len(parts) >= 2:
                name, value = parts[0].strip(), parts[1].strip()
                domain = parts[2].strip() if len(parts) > 2 else None
                await tab.set_cookie(name=name, value=value, domain=domain)
                session.comments.append(f"🍪 Кука установлена: {name}")
            else:
                session.comments.append("❌ Формат: name|value|domain")
        
        elif action == "clear_cookies":
            await tab.clear_browser_cookies()
            session.comments.append("🍪 Все куки очищены")
        
        # ============================================================
        # JAVASCRIPT
        # ============================================================
        elif action == "execute_js":
            try:
                result = await tab.execute_script(text)
                result_str = str(result)
                session.comments.append(f"⚡ JS результат: {result_str[:100]}")
            except Exception as e:
                session.comments.append(f"❌ Ошибка JS: {str(e)}")
        
        elif action == "execute_js_on_element":
            parts = text.split('|', 1)
            if len(parts) == 2:
                selector, script = parts[0].strip(), parts[1].strip()
                try:
                    element = await tab.query(selector)
                    result = await tab.execute_script(script, element=element)
                    session.comments.append(f"⚡ JS на элементе: {str(result)[:100]}")
                except:
                    session.comments.append(f"❌ Ошибка JS на элементе")
            else:
                session.comments.append("❌ Формат: selector|script")
        
        # ============================================================
        # ОЖИДАНИЕ
        # ============================================================
        elif action == "wait":
            seconds = float(text) if text else 1
            session.comments.append(f"⏳ Жду {seconds}с")
            await asyncio.sleep(seconds)
            session.comments.append("✅ Готово")
        
        elif action == "wait_for_element":
            parts = text.split('|', 1)
            selector = parts[0].strip()
            timeout = int(parts[1]) if len(parts) > 1 else 10
            try:
                await tab.find(selector, timeout=timeout)
                session.comments.append(f"✅ Элемент появился: {selector}")
            except:
                session.comments.append(f"❌ Элемент не появился: {selector}")
        
        elif action == "wait_for_visible":
            try:
                element = await tab.query(text)
                await element.wait_until(is_visible=True, timeout=10)
                session.comments.append(f"✅ Элемент видим: {text}")
            except:
                session.comments.append(f"❌ Элемент не стал видимым: {text}")
        
        # ============================================================
        # КУКИ (расширенные)
        # ============================================================
        elif action == "get_all_cookies":
            cookies = await browser.get_cookies(browser_context_id=session.context_id)
            session.comments.append(f"🍪 Всего кук в браузере: {len(cookies)}")
            for cookie in cookies[:5]:
                session.comments.append(f"  • {cookie.get('name')}")
        
        elif action == "delete_cookie":
            try:
                await tab.delete_cookie(text)
                session.comments.append(f"🍪 Кука удалена: {text}")
            except:
                session.comments.append(f"❌ Не удалось удалить куку: {text}")
        
        elif action == "clear_all_cookies":
            await tab.clear_browser_cookies()
            session.comments.append("🍪 Все куки очищены")
        
        # ============================================================
        # ОКНА БРАУЗЕРА
        # ============================================================
        elif action == "set_window_maximized":
            await tab.set_window_maximized()
            session.comments.append("🖥️ Окно развернуто")
        
        elif action == "set_window_minimized":
            await tab.set_window_minimized()
            session.comments.append("🖥️ Окно свернуто")
        
        elif action == "set_window_fullscreen":
            await tab.set_window_fullscreen()
            session.comments.append("🖥️ Полноэкранный режим")
        
        elif action == "get_window_bounds":
            bounds = await tab.get_window_bounds()
            session.comments.append(f"🖥️ Размеры: {bounds}")
        
        # ============================================================
        # SHADOW DOM
        # ============================================================
        elif action == "get_shadow_root":
            try:
                element = await tab.query(text)
                shadow = await element.get_shadow_root()
                session.shadow_roots.append(shadow)
                session.comments.append(f"🌑 Получен shadow root для {text}")
            except:
                session.comments.append(f"❌ Не удалось получить shadow root: {text}")
        
        elif action == "find_shadow_roots":
            try:
                roots = await tab.find_shadow_roots(deep=True, timeout=5)
                session.comments.append(f"🌑 Найдено shadow roots: {len(roots)}")
            except:
                session.comments.append("❌ Не удалось найти shadow roots")
        
        # ============================================================
        # HTTP ЗАПРОСЫ
        # ============================================================
        elif action == "http_get":
            try:
                response = await tab.request.get(text)
                session.comments.append(f"🌐 GET: {response.status_code}")
            except:
                session.comments.append(f"❌ Ошибка GET запроса: {text}")
        
        elif action == "http_post":
            parts = text.split('|', 1)
            if len(parts) == 2:
                url, data = parts[0].strip(), parts[1].strip()
                try:
                    response = await tab.request.post(url, json=json.loads(data))
                    session.comments.append(f"🌐 POST: {response.status_code}")
                except:
                    session.comments.append(f"❌ Ошибка POST запроса")
            else:
                session.comments.append("❌ Формат: url|json_data")
        
        # ============================================================
        # ЗАКРЫТИЕ
        # ============================================================
        elif action == "close":
            await session_manager.close_session(user_id)
            context.user_data.pop('view_message_id', None)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🔒 Браузер закрыт"
            )
            return
        
        else:
            session.comments.append(f"❌ Неизвестное действие: {action}")
        
    except Exception as e:
        session.comments.append(f"❌ Ошибка: {str(e)}")
    
    await update_window(update, context, user_id)

# ============================================================
# ОБРАБОТКА AI - РАСШИРЕННАЯ
# ============================================================

async def process_with_ai(user_message: str, user_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    global agnes_client
    
    if agnes_client is None:
        init_agnes()
    
    session = await session_manager.get_session(user_id)
    
    if session.waiting_for_input:
        session.waiting_for_input = False
        action = session.pending_action
        
        if action == "search":
            await execute_action("type_into_search", user_id, update, context, user_message)
        elif action == "go_to_url":
            await execute_action("go_to_url", user_id, update, context, user_message)
        elif action == "js":
            await execute_action("execute_js", user_id, update, context, user_message)
        elif action == "data":
            await execute_action("extract_data", user_id, update, context, user_message)
        elif action == "click":
            await execute_action("click", user_id, update, context, user_message)
        elif action == "type_text":
            await execute_action("type_text", user_id, update, context, user_message)
        return
    
    # РАСШИРЕННЫЙ ПРОМТ
    system_prompt = f"""
Ты — AI агент, управляющий браузером через Pydoll.

**ТЕКУЩЕЕ СОСТОЯНИЕ:**
- URL: {session.current_url or 'не загружен'}
- Заголовок: {session.page_title or 'не загружен'}
- Браузер: {'открыт' if session.is_active else 'закрыт'}
- Куки: {'установлены' if session.cookies_set else 'не установлены'}
- Вкладок: {len(session.tabs)}

**ВСЕ ВОЗМОЖНОСТИ (инструменты):**

📌 НАВИГАЦИЯ:
- go_to_url(url) - перейти на сайт
- go_back() - назад
- go_forward() - вперёд
- refresh() - обновить
- new_tab() - новая вкладка
- close_tab() - закрыть вкладку
- switch_tab(index) - переключить вкладку

🔍 ПОИСК:
- find_element(selector) - по CSS
- find_element_by_xpath(xpath) - по XPath
- find_element_by_text(text) - по тексту
- find_all_elements(selector) - все элементы

🖱️ ВЗАИМОДЕЙСТВИЕ:
- click(selector) - клик
- click_humanize(selector) - клик как человек
- type_text(selector|text) - ввод текста
- type_text_humanize(selector|text) - ввод как человек
- clear(selector) - очистить поле
- get_text(selector) - получить текст
- get_attribute(selector|attr) - получить атрибут
- get_value(selector) - получить значение
- is_visible(selector) - проверить видимость
- is_enabled(selector) - проверить доступность

📜 ПРОКРУТКА:
- scroll_up(amount) - вверх
- scroll_down(amount) - вниз
- scroll_to_element(selector) - к элементу
- scroll_to_top() - вверх
- scroll_to_bottom() - вниз

📸 СКРИНШОТЫ:
- screenshot() - всей страницы
- screenshot_full_page() - полная страница
- screenshot_element(selector) - элемента

📊 ДАННЫЕ:
- get_page_title() - заголовок
- get_current_url() - URL
- get_page_source() - HTML
- get_cookies() - все куки
- set_cookie(name|value|domain) - установить куку
- clear_cookies() - очистить куки

⚡ JAVASCRIPT:
- execute_js(script) - выполнить JS
- execute_js_on_element(selector|script) - JS на элементе

🔄 ОЖИДАНИЕ:
- wait(seconds) - подождать
- wait_for_element(selector|timeout) - ждать элемент
- wait_for_visible(selector) - ждать видимость

🌑 SHADOW DOM:
- get_shadow_root(selector) - получить shadow root
- find_shadow_roots() - найти все shadow roots

🌐 СЕТЬ:
- http_get(url) - GET запрос
- http_post(url|json) - POST запрос

🖥️ ОКНА:
- set_window_maximized() - развернуть
- set_window_minimized() - свернуть
- set_window_fullscreen() - полноэкранный

**ПРАВИЛА:**
1. Всегда проверяй, что браузер открыт
2. Используй правильные инструменты для задачи
3. Если элемент не найден - пробуй другие способы
4. Всегда сообщай о результате
5. Если запрос неполный - задай уточняющий вопрос
6. Для ввода текста используй формат: selector|текст
7. Для атрибутов: selector|атрибут
8. Для POST: url|{"key":"value"}
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
                
                # Навигация
                if tool_name == "go_to_url":
                    await execute_action("go_to_url", user_id, update, context, arguments.get("url", ""))
                elif tool_name == "go_back":
                    await execute_action("go_back", user_id, update, context)
                elif tool_name == "go_forward":
                    await execute_action("go_forward", user_id, update, context)
                elif tool_name == "refresh":
                    await execute_action("refresh", user_id, update, context)
                elif tool_name == "new_tab":
                    await execute_action("new_tab", user_id, update, context)
                elif tool_name == "close_tab":
                    await execute_action("close_tab", user_id, update, context)
                elif tool_name == "switch_tab":
                    await execute_action("switch_tab", user_id, update, context, str(arguments.get("index", 1)))
                
                # Поиск
                elif tool_name == "find_element":
                    await execute_action("find_element", user_id, update, context, arguments.get("selector", ""))
                elif tool_name == "find_element_by_xpath":
                    await execute_action("find_element_by_xpath", user_id, update, context, arguments.get("xpath", ""))
                elif tool_name == "find_element_by_text":
                    await execute_action("find_element_by_text", user_id, update, context, arguments.get("text", ""))
                elif tool_name == "find_all_elements":
                    await execute_action("find_all_elements", user_id, update, context, arguments.get("selector", ""))
                
                # Взаимодействие
                elif tool_name == "click":
                    await execute_action("click", user_id, update, context, arguments.get("selector", ""))
                elif tool_name == "click_humanize":
                    await execute_action("click_humanize", user_id, update, context, arguments.get("selector", ""))
                elif tool_name == "type_text":
                    selector = arguments.get("selector", "")
                    text = arguments.get("text", "")
                    await execute_action("type_text", user_id, update, context, f"{selector}|{text}")
                elif tool_name == "type_text_humanize":
                    selector = arguments.get("selector", "")
                    text = arguments.get("text", "")
                    await execute_action("type_text_humanize", user_id, update, context, f"{selector}|{text}")
                elif tool_name == "clear":
                    await execute_action("clear", user_id, update, context, arguments.get("selector", ""))
                elif tool_name == "get_text":
                    await execute_action("get_text", user_id, update, context, arguments.get("selector", ""))
                elif tool_name == "get_attribute":
                    selector = arguments.get("selector", "")
                    attr = arguments.get("attribute", "")
                    await execute_action("get_attribute", user_id, update, context, f"{selector}|{attr}")
                elif tool_name == "get_value":
                    await execute_action("get_value", user_id, update, context, arguments.get("selector", ""))
                elif tool_name == "is_visible":
                    await execute_action("is_visible", user_id, update, context, arguments.get("selector", ""))
                elif tool_name == "is_enabled":
                    await execute_action("is_enabled", user_id, update, context, arguments.get("selector", ""))
                
                # Прокрутка
                elif tool_name == "scroll_up":
                    await execute_action("scroll_up", user_id, update, context, str(arguments.get("amount", 300)))
                elif tool_name == "scroll_down":
                    await execute_action("scroll_down", user_id, update, context, str(arguments.get("amount", 300)))
                elif tool_name == "scroll_to_element":
                    await execute_action("scroll_to_element", user_id, update, context, arguments.get("selector", ""))
                elif tool_name == "scroll_to_top":
                    await execute_action("scroll_to_top", user_id, update, context)
                elif tool_name == "scroll_to_bottom":
                    await execute_action("scroll_to_bottom", user_id, update, context)
                
                # Скриншоты
                elif tool_name == "screenshot":
                    await execute_action("screenshot", user_id, update, context)
                    # Возвращаем скриншот отдельно
                    if session.last_screenshot:
                        return {"type": "screenshot", "data": session.last_screenshot}
                elif tool_name == "screenshot_full_page":
                    await execute_action("screenshot_full_page", user_id, update, context)
                    if session.last_screenshot:
                        return {"type": "screenshot", "data": session.last_screenshot}
                elif tool_name == "screenshot_element":
                    await execute_action("screenshot_element", user_id, update, context, arguments.get("selector", ""))
                    if session.last_screenshot:
                        return {"type": "screenshot", "data": session.last_screenshot}
                
                # Данные
                elif tool_name == "get_page_title":
                    await execute_action("get_page_title", user_id, update, context)
                elif tool_name == "get_current_url":
                    await execute_action("get_current_url", user_id, update, context)
                elif tool_name == "get_page_source":
                    await execute_action("get_page_source", user_id, update, context)
                elif tool_name == "get_cookies":
                    await execute_action("get_cookies", user_id, update, context)
                elif tool_name == "set_cookie":
                    name = arguments.get("name", "")
                    value = arguments.get("value", "")
                    domain = arguments.get("domain", "")
                    await execute_action("set_cookie", user_id, update, context, f"{name}|{value}|{domain}")
                elif tool_name == "clear_cookies":
                    await execute_action("clear_cookies", user_id, update, context)
                
                # JavaScript
                elif tool_name == "execute_js":
                    await execute_action("execute_js", user_id, update, context, arguments.get("script", ""))
                elif tool_name == "execute_js_on_element":
                    selector = arguments.get("selector", "")
                    script = arguments.get("script", "")
                    await execute_action("execute_js_on_element", user_id, update, context, f"{selector}|{script}")
                
                # Ожидание
                elif tool_name == "wait":
                    await execute_action("wait", user_id, update, context, str(arguments.get("seconds", 1)))
                elif tool_name == "wait_for_element":
                    selector = arguments.get("selector", "")
                    timeout = str(arguments.get("timeout", 10))
                    await execute_action("wait_for_element", user_id, update, context, f"{selector}|{timeout}")
                elif tool_name == "wait_for_visible":
                    await execute_action("wait_for_visible", user_id, update, context, arguments.get("selector", ""))
                
                # Shadow DOM
                elif tool_name == "get_shadow_root":
                    await execute_action("get_shadow_root", user_id, update, context, arguments.get("selector", ""))
                elif tool_name == "find_shadow_roots":
                    await execute_action("find_shadow_roots", user_id, update, context)
                
                # HTTP
                elif tool_name == "http_get":
                    await execute_action("http_get", user_id, update, context, arguments.get("url", ""))
                elif tool_name == "http_post":
                    url = arguments.get("url", "")
                    data = arguments.get("data", "{}")
                    await execute_action("http_post", user_id, update, context, f"{url}|{json.dumps(data)}")
                
                # Окна
                elif tool_name == "set_window_maximized":
                    await execute_action("set_window_maximized", user_id, update, context)
                elif tool_name == "set_window_minimized":
                    await execute_action("set_window_minimized", user_id, update, context)
                elif tool_name == "set_window_fullscreen":
                    await execute_action("set_window_fullscreen", user_id, update, context)
                elif tool_name == "get_window_bounds":
                    await execute_action("get_window_bounds", user_id, update, context)
                
                # Вопрос
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
# ИНСТРУМЕНТЫ ДЛЯ AI (РАСШИРЕННЫЕ)
# ============================================================

TOOLS = [
    # Навигация
    {"type": "function", "function": {"name": "go_to_url", "description": "Переходит на URL", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "go_back", "description": "Назад", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "go_forward", "description": "Вперёд", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "refresh", "description": "Обновить страницу", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "new_tab", "description": "Новая вкладка", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "close_tab", "description": "Закрыть вкладку", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "switch_tab", "description": "Переключить вкладку", "parameters": {"type": "object", "properties": {"index": {"type": "integer"}}, "required": ["index"]}}},
    
    # Поиск
    {"type": "function", "function": {"name": "find_element", "description": "Найти элемент по CSS", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}}},
    {"type": "function", "function": {"name": "find_element_by_xpath", "description": "Найти по XPath", "parameters": {"type": "object", "properties": {"xpath": {"type": "string"}}, "required": ["xpath"]}}},
    {"type": "function", "function": {"name": "find_element_by_text", "description": "Найти по тексту", "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "find_all_elements", "description": "Найти все элементы", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}}}},
    
    # Взаимодействие
    {"type": "function", "function": {"name": "click", "description": "Кликнуть", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}}},
    {"type": "function", "function": {"name": "click_humanize", "description": "Кликнуть как человек", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}}},
    {"type": "function", "function": {"name": "type_text", "description": "Ввести текст", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}, "text": {"type": "string"}}, "required": ["selector", "text"]}}},
    {"type": "function", "function": {"name": "type_text_humanize", "description": "Ввести текст как человек", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}, "text": {"type": "string"}}, "required": ["selector", "text"]}}},
    {"type": "function", "function": {"name": "clear", "description": "Очистить поле", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}}},
    {"type": "function", "function": {"name": "get_text", "description": "Получить текст", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}}},
    {"type": "function", "function": {"name": "get_attribute", "description": "Получить атрибут", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}, "attribute": {"type": "string"}}, "required": ["selector", "attribute"]}}},
    {"type": "function", "function": {"name": "get_value", "description": "Получить значение", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}}},
    {"type": "function", "function": {"name": "is_visible", "description": "Проверить видимость", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}}},
    {"type": "function", "function": {"name": "is_enabled", "description": "Проверить доступность", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}}},
    
    # Прокрутка
    {"type": "function", "function": {"name": "scroll_up", "description": "Прокрутить вверх", "parameters": {"type": "object", "properties": {"amount": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "scroll_down", "description": "Прокрутить вниз", "parameters": {"type": "object", "properties": {"amount": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "scroll_to_element", "description": "Прокрутить к элементу", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}}},
    {"type": "function", "function": {"name": "scroll_to_top", "description": "Прокрутить вверх страницы", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "scroll_to_bottom", "description": "Прокрутить вниз страницы", "parameters": {"type": "object", "properties": {}}}},
    
    # Скриншоты
    {"type": "function", "function": {"name": "screenshot", "description": "Скриншот страницы", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "screenshot_full_page", "description": "Полный скриншот страницы", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "screenshot_element", "description": "Скриншот элемента", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}}},
    
    # Данные
    {"type": "function", "function": {"name": "get_page_title", "description": "Заголовок страницы", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_current_url", "description": "Текущий URL", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_page_source", "description": "HTML код", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_cookies", "description": "Все куки", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "set_cookie", "description": "Установить куку", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "value": {"type": "string"}, "domain": {"type": "string"}}, "required": ["name", "value"]}}},
    {"type": "function", "function": {"name": "clear_cookies", "description": "Очистить куки", "parameters": {"type": "object", "properties": {}}}},
    
    # JavaScript
    {"type": "function", "function": {"name": "execute_js", "description": "Выполнить JavaScript", "parameters": {"type": "object", "properties": {"script": {"type": "string"}}, "required": ["script"]}}},
    {"type": "function", "function": {"name": "execute_js_on_element", "description": "JS на элементе", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}, "script": {"type": "string"}}, "required": ["selector", "script"]}}},
    
    # Ожидание
    {"type": "function", "function": {"name": "wait", "description": "Подождать секунд", "parameters": {"type": "object", "properties": {"seconds": {"type": "number"}}}}},
    {"type": "function", "function": {"name": "wait_for_element", "description": "Ждать появления элемента", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["selector"]}}},
    {"type": "function", "function": {"name": "wait_for_visible", "description": "Ждать видимости элемента", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}}},
    
    # Shadow DOM
    {"type": "function", "function": {"name": "get_shadow_root", "description": "Получить shadow root", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}}},
    {"type": "function", "function": {"name": "find_shadow_roots", "description": "Найти все shadow roots", "parameters": {"type": "object", "properties": {}}}},
    
    # HTTP
    {"type": "function", "function": {"name": "http_get", "description": "GET запрос", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "http_post", "description": "POST запрос", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "data": {"type": "object"}}, "required": ["url"]}}},
    
    # Окна
    {"type": "function", "function": {"name": "set_window_maximized", "description": "Развернуть окно", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "set_window_minimized", "description": "Свернуть окно", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "set_window_fullscreen", "description": "Полноэкранный режим", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_window_bounds", "description": "Размеры окна", "parameters": {"type": "object", "properties": {}}}},
    
    # Вопрос
    {"type": "function", "function": {"name": "ask", "description": "Задать вопрос пользователю", "parameters": {"type": "object", "properties": {"question": {"type": "string"}, "action": {"type": "string", "enum": ["search", "go_to_url", "js", "data", "click", "type_text"]}}, "required": ["question"]}}},
]

# ============================================================
# КОМАНДЫ
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот с полным контролем браузера\n\n"
        "✅ Все возможности Pydoll доступны\n"
        "🍪 Куки X.com установлены\n\n"
        "Просто напиши что нужно сделать:\n"
        "• Найди котиков на YouTube\n"
        "• Кликни на кнопку 'Войти'\n"
        "• Сделай скриншот элемента\n"
        "• Выполни JS код\n\n"
        "Команды:\n"
        "/open - Открыть браузер\n"
        "/close - Закрыть браузер"
    )

async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = await session_manager.get_session(user_id)
    session.comments = ["🟢 Браузер открыт", "✅ Все возможности доступны"]
    await update_window(update, context, user_id)

async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await session_manager.close_session(user_id)
    context.user_data.pop('view_message_id', None)
    await update.message.reply_text("🔒 Браузер закрыт")

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        session.pending_action = "type_into_search"
        session.comments.append("✏️ Напиши текст для поиска")
        await update_window(update, context, user_id)
    
    elif data == "menu_screenshot":
        await execute_action("screenshot", user_id, update, context)
    
    elif data == "menu_up":
        await execute_action("scroll_up", user_id, update, context, "300")
    
    elif data == "menu_down":
        await execute_action("scroll_down", user_id, update, context, "300")
    
    elif data == "menu_refresh":
        await execute_action("refresh", user_id, update, context)
    
    elif data == "menu_back":
        await execute_action("go_back", user_id, update, context)
    
    elif data == "menu_js":
        session.waiting_for_input = True
        session.pending_action = "execute_js"
        session.comments.append("✏️ Напиши JavaScript код")
        await update_window(update, context, user_id)
    
    elif data == "menu_data":
        session.waiting_for_input = True
        session.pending_action = "extract_data"
        session.comments.append("✏️ Напиши CSS селектор")
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
            "x": "x.com",
        }
        if site in sites:
            await execute_action("go_to_url", user_id, update, context, sites[site])

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if text.startswith('/'):
        return
    
    session = await session_manager.get_session(user_id)
    
    if not session.tab:
        await update.message.reply_text("❌ Сначала открой браузер: /open")
        return
    
    if session.waiting_for_input:
        action = session.pending_action
        session.waiting_for_input = False
        
        if action == "type_into_search":
            await execute_action("type_into_search", user_id, update, context, text)
        elif action == "go_to_url":
            await execute_action("go_to_url", user_id, update, context, text)
        elif action == "execute_js":
            await execute_action("execute_js", user_id, update, context, text)
        elif action == "extract_data":
            await execute_action("extract_data", user_id, update, context, text)
        elif action == "click":
            await execute_action("click", user_id, update, context, text)
        elif action == "type_text":
            await execute_action("type_text", user_id, update, context, text)
        return
    
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
        logger.info("🚀 Бот с ПОЛНЫМ контролем браузера запущен!")
        logger.info("📌 Все возможности Pydoll доступны")
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