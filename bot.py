import os
import sys
import subprocess
import logging
import asyncio
import base64
import json
import random
from datetime import datetime
from typing import Optional, List, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ========== PYDANTIC ==========
try:
    from pydantic import BaseModel, Field, ValidationError
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False

# ========== НАСТРОЙКА ЛОГГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# ========== ПРОВЕРКА CHROMIUM ==========
CHROMIUM_PATH = None
CHROMIUM_INSTALLED = False

def check_chromium():
    global CHROMIUM_PATH, CHROMIUM_INSTALLED
    chromium_paths = [
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable'
    ]
    for path in chromium_paths:
        if os.path.exists(path):
            CHROMIUM_PATH = path
            CHROMIUM_INSTALLED = True
            logger.info(f"✅ Chromium найден: {path}")
            return True
    return False

check_chromium()

# ========== ПРОВЕРКА PYDOLL ==========
PYDOLL_AVAILABLE = False

try:
    from pydoll.browser import Chrome
    from pydoll.browser.options import ChromiumOptions
    PYDOLL_AVAILABLE = True
    logger.info("✅ Pydoll загружен")
except ImportError as e:
    logger.warning(f"⚠️ Pydoll не найден: {e}")

# ========== PYDANTIC МОДЕЛИ ==========
if PYDANTIC_AVAILABLE:
    class TweetModel(BaseModel):
        text: str = Field(..., description="Текст твита")
        author: Optional[str] = Field(None, description="Автор")
        time: Optional[str] = Field(None, description="Время")
        is_pinned: bool = Field(False, description="Закреплен")
        likes: Optional[int] = Field(0, description="Лайки")
        retweets: Optional[int] = Field(0, description="Ретвиты")
        
    class ApiResponseModel(BaseModel):
        url: str = Field(..., description="URL запроса")
        status: int = Field(..., description="Статус ответа")
        ok: bool = Field(..., description="Успешно")
        data: Dict[str, Any] = Field(default_factory=dict, description="Данные")
        
    class ShadowElementModel(BaseModel):
        tag: str = Field(..., description="Тег элемента")
        id: Optional[str] = Field(None, description="ID")
        class_name: Optional[str] = Field(None, description="Класс")
        children_count: int = Field(0, description="Количество детей")
        
    class ExtractedDataModel(BaseModel):
        source: str = Field(..., description="Источник")
        data: List[Dict[str, Any]] = Field(default_factory=list, description="Данные")
        count: int = Field(0, description="Количество")

# ========== КУКИ X.COM ==========
COOKIES = [
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
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "__cf_bm",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "3PHty0MUYSrud60gKo41iFni0wDB5uFEa.TAyF3eWFQ-1783076730.4783854-1.0.1.1-tIYvV5IeAbbckRKhliuQ8DI9NYoY6JmPZJdARb6ixRKFjmT7KZAh51b0nLs.b7Luev2xSanCGZe_nfRDp8grfYUFb86myqghHqcGrGpymnU2..9obAQIOtsQQ7mUYWo0"
    }
]

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
pydoll_browser = None
pydoll_tab = None
login_status = {
    'is_logged_in': False,
    'username': None,
    'last_check': None
}

# ========== БРАУЗЕРНАЯ ЛОГИКА ==========

def random_delay(min_sec=0.5, max_sec=2.0):
    return random.uniform(min_sec, max_sec)

async def human_goto(page, url):
    try:
        if hasattr(page, 'go_to'):
            await page.go_to(url, humanize=True)
        else:
            await page.go_to(url)
        await asyncio.sleep(random_delay(1.5, 3.5))
    except Exception as e:
        logger.warning(f"Human goto error: {e}")
        await page.go_to(url)

async def human_scroll(page, amount=300):
    try:
        if hasattr(page, 'scroll_by'):
            await page.scroll_by(amount, humanize=True)
        else:
            await page.execute_script(f'window.scrollBy(0, {amount})')
        await asyncio.sleep(random_delay(0.3, 1.0))
    except Exception as e:
        logger.warning(f"Human scroll error: {e}")
        await page.execute_script(f'window.scrollBy(0, {amount})')

async def get_pydoll_browser():
    global pydoll_browser, pydoll_tab
    
    if pydoll_browser and pydoll_tab:
        try:
            await pydoll_tab.execute_script('1')
            return pydoll_tab
        except:
            await close_pydoll_browser()
    
    if not PYDOLL_AVAILABLE or not CHROMIUM_INSTALLED:
        return None
    
    try:
        options = ChromiumOptions()
        options.binary_location = CHROMIUM_PATH
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--headless=new")
        
        pydoll_browser = Chrome(options=options)
        pydoll_tab = await pydoll_browser.start()
        await pydoll_tab.go_to('https://x.com')
        await asyncio.sleep(2)
        
        return pydoll_tab
    except Exception as e:
        logger.error(f"❌ Ошибка запуска Pydoll: {e}")
        return None

async def close_pydoll_browser():
    global pydoll_browser, pydoll_tab
    if pydoll_browser:
        try:
            await pydoll_browser.close()
        except:
            pass
        pydoll_browser = None
        pydoll_tab = None

async def get_browser():
    return await get_pydoll_browser()

async def execute_js(script):
    page = await get_browser()
    if page is None:
        return None
    try:
        if hasattr(page, 'execute_script'):
            return await page.execute_script(script)
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка JS: {e}")
        return None

async def take_screenshot():
    page = await get_browser()
    if page is None:
        return None
    try:
        if hasattr(page, 'take_screenshot'):
            screenshot_base64 = await page.take_screenshot(as_base64=True)
            if screenshot_base64:
                return base64.b64decode(screenshot_base64)
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка скриншота: {e}")
        return None

# ========== SHADOW DOM ==========

async def shadow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Работа с Shadow DOM - поиск веб-компонентов"""
    logger.info(f"📩 /shadow от {update.effective_user.username}")
    
    await send_message_safe(update, "🛡️ Исследую Shadow DOM...")
    
    try:
        page = await get_browser()
        if page is None:
            await send_message_safe(update, "❌ Браузер не запущен. Используйте /login")
            return
        
        # 1. Находим все элементы с shadowRoot
        js_find = """
            () => {
                const result = [];
                document.querySelectorAll('*').forEach(el => {
                    if (el.shadowRoot) {
                        const children = el.shadowRoot.children.length;
                        result.push({
                            tag: el.tagName.toLowerCase(),
                            id: el.id || null,
                            class_name: el.className || null,
                            children_count: children
                        });
                    }
                });
                return result;
            }
        """
        
        shadow_elements = await page.execute_script(js_find)
        
        if not shadow_elements or len(shadow_elements) == 0:
            await send_message_safe(update, "⚠️ Shadow DOM элементы не найдены на странице.")
            return
        
        # Валидация через Pydantic
        validated_elements = []
        if PYDANTIC_AVAILABLE:
            for el in shadow_elements:
                try:
                    validated = ShadowElementModel(**el)
                    validated_elements.append(validated.model_dump())
                except ValidationError as e:
                    logger.warning(f"⚠️ Ошибка валидации: {e}")
                    validated_elements.append(el)
        else:
            validated_elements = shadow_elements
        
        # 2. Пробуем получить содержимое первого shadowRoot
        js_get_content = """
            () => {
                const result = [];
                document.querySelectorAll('*').forEach(el => {
                    if (el.shadowRoot) {
                        const items = [];
                        for (let child of el.shadowRoot.children) {
                            items.push({
                                tag: child.tagName.toLowerCase(),
                                text: child.textContent ? child.textContent.slice(0, 100) : '',
                                id: child.id || null
                            });
                        }
                        result.push({
                            host: el.tagName.toLowerCase(),
                            children: items.slice(0, 5)
                        });
                    }
                });
                return result.slice(0, 3);
            }
        """
        
        shadow_content = await page.execute_script(js_get_content)
        
        # Формируем ответ
        response = f"🛡️ **SHADOW DOM**\n\n"
        response += f"📦 Найдено элементов: {len(validated_elements)}\n\n"
        
        for i, el in enumerate(validated_elements[:5], 1):
            response += f"**{i}.** `{el.get('tag', 'unknown')}`"
            if el.get('id'):
                response += f" id=\"{el['id']}\""
            if el.get('class_name'):
                response += f" class=\"{el['class_name']}\""
            response += f"\n   📄 Детей: {el.get('children_count', 0)}\n\n"
        
        if shadow_content and len(shadow_content) > 0:
            response += "📋 **Содержимое shadowRoot:**\n\n"
            for item in shadow_content[:2]:
                response += f"🏷️ Хост: `{item.get('host', 'unknown')}`\n"
                for child in item.get('children', [])[:3]:
                    response += f"  └─ {child.get('tag', '')}"
                    if child.get('text'):
                        text = child['text'].replace('\n', ' ')[:50]
                        response += f" \"{text}...\""
                    response += "\n"
                response += "\n"
        
        # Инструкция по работе с Shadow DOM
        response += "💡 **Как использовать:**\n"
        response += "```python\n"
        response += "# Найти хост-элемент\n"
        response += "host = await tab.find('#shadow-host')\n\n"
        response += "# Получить shadowRoot\n"
        response += "shadow_root = await host.get_shadow_root()\n\n"
        response += "# Искать внутри shadowRoot\n"
        response += "inner = await shadow_root.query('.inner-class')\n"
        response += "```"
        
        if len(response) > 4000:
            filename = f"shadow_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(validated_elements, f, indent=2, ensure_ascii=False)
            await update.message.reply_document(
                document=open(filename, 'rb'),
                caption=f"🛡️ Shadow DOM элементы ({len(validated_elements)})"
            )
        else:
            await send_message_safe(update, response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"❌ Ошибка shadow: {e}", exc_info=True)
        await send_message_safe(update, f"❌ Ошибка: {str(e)[:200]}")

# ========== API - ПЕРЕХВАТ И ВЫПОЛНЕНИЕ ЗАПРОСОВ ==========

async def api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнение API запросов через браузер с сессией"""
    logger.info(f"📩 /api от {update.effective_user.username} с аргументами: {context.args}")
    
    if not context.args:
        await update.message.reply_text(
            "🌐 **API запрос с сессией браузера**\n\n"
            "Использование: `/api <url>`\n"
            "Пример: `/api https://x.com/i/api/1.1/onboarding/task.json`\n\n"
            "⚠️ Запрос использует сессию браузера с вашими куками.\n"
            "Поддерживает GET и POST (укажите метод и тело)."
        )
        return
    
    url = context.args[0]
    method = context.args[1].upper() if len(context.args) > 1 else "GET"
    body = ' '.join(context.args[2:]) if len(context.args) > 2 else None
    
    await send_message_safe(update, f"🌐 Выполняю {method} запрос к {url[:80]}...")
    
    try:
        page = await get_browser()
        if page is None:
            await send_message_safe(update, "❌ Браузер не запущен. Используйте /login")
            return
        
        if not login_status['is_logged_in']:
            await send_message_safe(update, "❌ Вы не авторизованы. Используйте /login")
            return
        
        # Формируем JS код для запроса
        if method == "POST" and body:
            js_code = f"""
                (async () => {{
                    try {{
                        const response = await fetch('{url}', {{
                            method: 'POST',
                            credentials: 'include',
                            headers: {{
                                'Accept': 'application/json',
                                'Content-Type': 'application/json'
                            }},
                            body: JSON.stringify({body})
                        }});
                        
                        const data = await response.json();
                        return {{
                            status: response.status,
                            ok: response.ok,
                            data: data
                        }};
                    }} catch (e) {{
                        return {{
                            error: e.message,
                            status: 0
                        }};
                    }}
                }})()
            """
        else:
            js_code = f"""
                (async () => {{
                    try {{
                        const response = await fetch('{url}', {{
                            method: 'GET',
                            credentials: 'include',
                            headers: {{
                                'Accept': 'application/json',
                            }}
                        }});
                        
                        const data = await response.json();
                        return {{
                            status: response.status,
                            ok: response.ok,
                            data: data
                        }};
                    }} catch (e) {{
                        return {{
                            error: e.message,
                            status: 0
                        }};
                    }}
                }})()
            """
        
        result = await page.execute_script(js_code)
        
        if result.get('error'):
            await send_message_safe(update, f"❌ Ошибка: {result['error']}")
            return
        
        # Валидация через Pydantic
        if PYDANTIC_AVAILABLE:
            try:
                validated = ApiResponseModel(
                    url=url,
                    status=result.get('status', 0),
                    ok=result.get('ok', False),
                    data=result.get('data', {})
                )
                result = validated.model_dump()
            except ValidationError as e:
                logger.warning(f"⚠️ Ошибка валидации API: {e}")
        
        response_text = f"✅ **API ЗАПРОС ВЫПОЛНЕН**\n\n"
        response_text += f"📍 {url[:80]}\n"
        response_text += f"📊 Статус: {result.get('status', 0)}\n"
        response_text += f"📊 Успешно: {'✅' if result.get('ok') else '❌'}\n\n"
        
        data = result.get('data', {})
        if data:
            if isinstance(data, dict):
                data_str = json.dumps(data, indent=2, ensure_ascii=False)[:1500]
            else:
                data_str = str(data)[:1500]
            response_text += f"📝 **Данные:**\n```json\n{data_str}\n```"
        else:
            response_text += "⚠️ Данные не получены"
        
        if len(response_text) > 4000:
            filename = f"api_response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            await update.message.reply_document(
                document=open(filename, 'rb'),
                caption=f"📄 API ответ: {url[:50]}"
            )
        else:
            await send_message_safe(update, response_text, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"❌ Ошибка API: {e}", exc_info=True)
        await send_message_safe(update, f"❌ Ошибка: {str(e)[:200]}")

# ========== EXTRACT - СТРУКТУРИРОВАННОЕ ИЗВЛЕЧЕНИЕ ==========

async def extract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Структурированное извлечение данных со страницы"""
    logger.info(f"📩 /extract от {update.effective_user.username}")
    
    await send_message_safe(update, "📊 Извлекаю структурированные данные...")
    
    try:
        page = await get_browser()
        if page is None:
            await send_message_safe(update, "❌ Браузер не запущен. Используйте /login")
            return
        
        # Извлекаем твиты со страницы
        js_extract = """
            () => {
                const tweets = [];
                document.querySelectorAll('[data-testid="tweet"]').forEach(el => {
                    const textEl = el.querySelector('[data-testid="tweetText"]');
                    const timeEl = el.querySelector('time');
                    const isPinned = !!el.querySelector('[data-testid="pinIcon"]');
                    
                    // Лайки
                    const likeBtn = el.querySelector('[data-testid="like"]');
                    let likes = 0;
                    if (likeBtn) {
                        const likeText = likeBtn.getAttribute('aria-label') || '';
                        const match = likeText.match(/(\\d+)/);
                        if (match) likes = parseInt(match[1]);
                    }
                    
                    // Ретвиты
                    const retweetBtn = el.querySelector('[data-testid="retweet"]');
                    let retweets = 0;
                    if (retweetBtn) {
                        const retweetText = retweetBtn.getAttribute('aria-label') || '';
                        const match = retweetText.match(/(\\d+)/);
                        if (match) retweets = parseInt(match[1]);
                    }
                    
                    // Автор
                    let author = null;
                    const userEl = el.querySelector('[data-testid="User-Name"]');
                    if (userEl) {
                        const link = userEl.querySelector('a');
                        if (link) {
                            const href = link.getAttribute('href');
                            if (href) {
                                const match = href.match(/^\\/([^\\/]+)/);
                                if (match) author = match[1];
                            }
                        }
                    }
                    
                    let text = textEl ? textEl.innerText : '';
                    text = text.replace(/https?:\\/\\/[^\\s]*/g, '');
                    text = text.replace(/\\s{2,}/g, ' ');
                    text = text.trim();
                    
                    if (text) {
                        tweets.push({
                            text: text,
                            author: author,
                            time: timeEl ? timeEl.getAttribute('datetime') : null,
                            is_pinned: isPinned,
                            likes: likes,
                            retweets: retweets
                        });
                    }
                });
                return tweets.slice(0, 20);
            }
        """
        
        extracted_data = await page.execute_script(js_extract)
        
        if not extracted_data or len(extracted_data) == 0:
            await send_message_safe(update, "⚠️ Нет данных для извлечения. Убедитесь, что на странице есть твиты.")
            return
        
        # Валидация через Pydantic
        validated_tweets = []
        if PYDANTIC_AVAILABLE:
            for tweet in extracted_data:
                try:
                    validated = TweetModel(**tweet)
                    validated_tweets.append(validated.model_dump())
                except ValidationError as e:
                    logger.warning(f"⚠️ Ошибка валидации твита: {e}")
                    validated_tweets.append(tweet)
        else:
            validated_tweets = extracted_data
        
        # Формируем структурированный вывод
        response = f"📊 **ИЗВЛЕЧЕНИЕ ДАННЫХ**\n\n"
        response += f"📌 Найдено: {len(validated_tweets)} твитов\n"
        response += f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        
        # Статистика
        if PYDANTIC_AVAILABLE:
            total_likes = sum([t.get('likes', 0) for t in validated_tweets])
            total_retweets = sum([t.get('retweets', 0) for t in validated_tweets])
            pinned = [t for t in validated_tweets if t.get('is_pinned')]
            
            response += f"❤️ Всего лайков: {total_likes}\n"
            response += f"🔄 Всего ретвитов: {total_retweets}\n"
            response += f"📌 Закреплено: {len(pinned)}\n\n"
        
        # Показываем первые 3 твита
        response += "📝 **Примеры:**\n\n"
        for i, tweet in enumerate(validated_tweets[:3], 1):
            text = tweet.get('text', '')[:150]
            if len(tweet.get('text', '')) > 150:
                text += "..."
            response += f"**{i}.** {text}\n"
            if tweet.get('author'):
                response += f"   👤 @{tweet['author']}"
            if tweet.get('likes', 0) > 0:
                response += f" ❤️ {tweet['likes']}"
            if tweet.get('retweets', 0) > 0:
                response += f" 🔄 {tweet['retweets']}"
            if tweet.get('is_pinned'):
                response += " 📌 ЗАКРЕПЛЕН"
            response += "\n\n"
        
        # Сохраняем в JSON
        filename = f"extracted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(validated_tweets, f, indent=2, ensure_ascii=False)
        
        # Отправляем результат
        if len(response) > 4000:
            await update.message.reply_document(
                document=open(filename, 'rb'),
                caption=f"📄 Извлечено {len(validated_tweets)} твитов"
            )
        else:
            await send_message_safe(update, response)
            await update.message.reply_document(
                document=open(filename, 'rb'),
                caption=f"📄 Полные данные ({len(validated_tweets)} твитов)"
            )
        
    except Exception as e:
        logger.error(f"❌ Ошибка extract: {e}", exc_info=True)
        await send_message_safe(update, f"❌ Ошибка: {str(e)[:200]}")

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

async def send_photo_safe(update, photo, caption=""):
    try:
        if update.callback_query:
            await update.callback_query.message.reply_photo(photo=photo, caption=caption)
        elif update.message:
            await update.message.reply_photo(photo=photo, caption=caption)
    except Exception as e:
        logger.error(f"❌ Ошибка отправки фото: {e}")

async def send_message_safe(update, text, parse_mode=None, reply_markup=None):
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        elif update.message:
            await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"❌ Ошибка отправки сообщения: {e}")

async def set_cookies_combined(page):
    try:
        for cookie in COOKIES:
            await page.set_cookie(
                name=cookie['name'],
                value=cookie['value'],
                domain=cookie.get('domain', '.x.com'),
                path=cookie.get('path', '/')
            )
        return True
    except:
        try:
            await page.execute_script('''
                document.cookie.split(";").forEach(function(c) {
                    document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/");
                });
            ''')
            for cookie in COOKIES:
                name = cookie['name']
                value = cookie['value'].replace("'", "\\'")
                domain = cookie.get('domain', '.x.com')
                path = cookie.get('path', '/')
                js_code = f"document.cookie = '{name}={value}; domain={domain}; path={path}';"
                await page.execute_script(js_code)
            return True
        except:
            return False

async def emulate_human_login_flow(page):
    try:
        await asyncio.sleep(random_delay(1, 3))
        await human_scroll(page, 200)
        await asyncio.sleep(random_delay(0.5, 1.5))
        await page.execute_script('window.scrollTo(0, 0);')
    except Exception as e:
        logger.warning(f"⚠️ Ошибка эмуляции: {e}")

async def check_login_status_detailed(page):
    try:
        js_code = """
            () => {
                const cookies = document.cookie.split(';').reduce((acc, c) => {
                    const [key, val] = c.trim().split('=');
                    if (key && val) acc[key] = val;
                    return acc;
                }, {});
                
                const hasAuthToken = !!cookies.auth_token && cookies.auth_token.length > 0;
                const hasCt0 = !!cookies.ct0 && cookies.ct0.length > 0;
                const hasProfileLink = !!document.querySelector('[data-testid="AppTabBar_Profile_Link"]');
                const hasTweetBtn = !!document.querySelector('[data-testid="tweetButton"]') || 
                                    !!document.querySelector('[data-testid="postButton"]');
                const hasSideNav = !!document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
                const hasLoginBtn = !!document.querySelector('[data-testid="loginButton"]');
                const hasLoginLink = !!document.querySelector('a[href="/login"]');
                const isOnLoginPage = window.location.href.includes('/login');
                
                let username = null;
                const profileLink = document.querySelector('[data-testid="AppTabBar_Profile_Link"] a');
                if (profileLink) {
                    const href = profileLink.getAttribute('href');
                    if (href) {
                        const match = href.match(/^\\/([^\\/]+)/);
                        if (match) username = match[1];
                    }
                }
                
                const hasUserElements = hasProfileLink || hasTweetBtn || hasSideNav;
                const hasLoginElements = hasLoginBtn || hasLoginLink;
                const isLoggedIn = hasAuthToken && hasUserElements && !hasLoginElements && !isOnLoginPage;
                
                return {
                    isLoggedIn: isLoggedIn,
                    username: username || null,
                    hasAuthToken: hasAuthToken,
                    hasCt0: hasCt0,
                    hasProfileLink: hasProfileLink,
                    hasTweetBtn: hasTweetBtn,
                    hasSideNav: hasSideNav,
                    hasLoginBtn: hasLoginBtn,
                    hasLoginLink: hasLoginLink,
                    isOnLoginPage: isOnLoginPage,
                    url: window.location.href
                };
            }
        """
        return await page.execute_script(js_code)
    except:
        return {'isLoggedIn': False}

# ========== КОМАНДА ЛОГИН ==========

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📩 /login от {update.effective_user.username}")
    await send_message_safe(update, "🚀 Запускаю браузер...")
    
    try:
        page = await get_browser()
        if page is None:
            await send_message_safe(update, "❌ Не удалось запустить браузер.")
            return
        
        await send_message_safe(update, "🌐 Захожу на X.com...")
        await human_goto(page, 'https://x.com')
        await asyncio.sleep(2)
        
        await send_message_safe(update, "🍪 Устанавливаю куки...")
        await set_cookies_combined(page)
        
        await send_message_safe(update, "🚶 Эмулирую поведение...")
        await emulate_human_login_flow(page)
        
        await send_message_safe(update, "🔄 Обновляю страницу...")
        await human_goto(page, 'https://x.com')
        await asyncio.sleep(3)
        
        await send_message_safe(update, "🔍 Проверяю авторизацию...")
        status_data = await check_login_status_detailed(page)
        
        global login_status
        login_status['is_logged_in'] = status_data.get('isLoggedIn', False)
        login_status['username'] = status_data.get('username')
        login_status['last_check'] = datetime.now()
        
        response = f"📊 **СТАТУС АВТОРИЗАЦИИ**\n\n"
        response += f"📍 URL: {status_data.get('url', 'unknown')}\n\n"
        response += f"🍪 auth_token: {'✅' if status_data.get('hasAuthToken') else '❌'}\n"
        response += f"🍪 ct0: {'✅' if status_data.get('hasCt0') else '❌'}\n\n"
        response += f"👤 Профиль: {'✅' if status_data.get('hasProfileLink') else '❌'}\n"
        response += f"📝 Твитнуть: {'✅' if status_data.get('hasTweetBtn') else '❌'}\n"
        response += f"⚙️ Меню: {'✅' if status_data.get('hasSideNav') else '❌'}\n\n"
        
        if status_data.get('isLoggedIn'):
            response += f"✅ **ВЫ АВТОРИЗОВАНЫ!**\n"
            if status_data.get('username'):
                response += f"👤 @{status_data['username']}\n"
            response += "\n💡 Бот готов к работе!"
        else:
            response += f"❌ **НЕ АВТОРИЗОВАН**\n\n"
            if status_data.get('isOnLoginPage'):
                response += "⚠️ Куки устарели. Обновите через /setcookies"
            elif not status_data.get('hasAuthToken'):
                response += "⚠️ auth_token отсутствует. Обновите куки"
            else:
                response += "⚠️ Попробуйте /login еще раз"
        
        await send_message_safe(update, response)
        
        screenshot = await take_screenshot()
        if screenshot:
            await send_photo_safe(
                update,
                screenshot,
                f"📸 X.com - {'✅ Авторизован' if status_data.get('isLoggedIn') else '❌ Не авторизован'}"
            )
        
    except Exception as e:
        logger.error(f"❌ Ошибка login: {e}", exc_info=True)
        await send_message_safe(update, f"❌ Ошибка: {str(e)[:200]}")

# ========== КОМАНДЫ ТЕЛЕГРАМ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔐 Авторизация", callback_data="login")],
        [InlineKeyboardButton("📸 Скриншот", callback_data="screen")],
        [InlineKeyboardButton("📊 Статус", callback_data="status")],
        [InlineKeyboardButton("📝 Твиты", callback_data="tweets")],
        [InlineKeyboardButton("🛡️ Shadow DOM", callback_data="shadow")],
        [InlineKeyboardButton("🌐 API Запрос", callback_data="api")],
        [InlineKeyboardButton("📊 Extract", callback_data="extract")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="close")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status_emoji = "✅" if login_status['is_logged_in'] else "❌"
    username_text = f" @{login_status['username']}" if login_status['username'] else ""
    
    await update.message.reply_text(
        f"🤖 **X.com Бот**\n\n"
        f"🔐 Статус: {status_emoji} {login_status['is_logged_in'] and 'Авторизован' or 'Не авторизован'}{username_text}\n"
        f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}\n"
        f"📦 Pydantic: {'✅' if PYDANTIC_AVAILABLE else '❌'}\n"
        f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}\n\n"
        f"📌 **Нажмите кнопку:**",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "login":
        await login(update, context)
    elif query.data == "screen":
        await screen(update, context)
    elif query.data == "status":
        await status(update, context)
    elif query.data == "tweets":
        await query.edit_message_text(
            "📝 **Введите username для парсинга твитов:**\n\n"
            "Пример: `/tweets elonmusk 5`"
        )
    elif query.data == "shadow":
        await shadow(update, context)
    elif query.data == "api":
        await query.edit_message_text(
            "🌐 **Введите URL для API запроса:**\n\n"
            "Пример: `/api https://x.com/i/api/1.1/onboarding/task.json`\n\n"
            "POST запрос: `/api <url> POST {\\\"key\\\":\\\"value\\\"}`"
        )
    elif query.data == "extract":
        await extract(update, context)
    elif query.data == "close":
        await close(update, context)

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_message_safe(update, "📸 Делаю скриншот...")
    try:
        screenshot = await take_screenshot()
        if screenshot:
            await send_photo_safe(update, screenshot, "📸 Скриншот X.com")
        else:
            await send_message_safe(update, "❌ Не удалось сделать скриншот")
    except Exception as e:
        await send_message_safe(update, f"❌ Ошибка: {str(e)[:100]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_text = f"📊 **СТАТУС БОТА**\n\n"
    status_text += f"🔐 Авторизация: {'✅' if login_status['is_logged_in'] else '❌'}\n"
    if login_status['username']:
        status_text += f"👤 @{login_status['username']}\n"
    status_text += f"🕐 {login_status['last_check'] or 'Никогда'}\n\n"
    status_text += f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}\n"
    status_text += f"📦 Pydantic: {'✅' if PYDANTIC_AVAILABLE else '❌'}\n"
    status_text += f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}\n"
    status_text += f"🌐 Браузер: {'✅' if pydoll_browser else '❌'}\n"
    status_text += f"🍪 Кук: {len(COOKIES)}"
    await send_message_safe(update, status_text, parse_mode='Markdown')

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_message_safe(update, "⏳ Закрываю браузер...")
    await close_pydoll_browser()
    await send_message_safe(update, "✅ Браузер закрыт!")

async def tweets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("ℹ️ Использование: /tweets <username> [count]")
        return
    
    username = context.args[0].replace('@', '').strip()
    count = int(context.args[1]) if len(context.args) > 1 else 10
    
    await send_message_safe(update, f"📊 Парсю твиты @{username}...")
    
    try:
        page = await get_browser()
        if page is None:
            await send_message_safe(update, "❌ Браузер не запущен")
            return
        
        await human_goto(page, f"https://x.com/{username}")
        await asyncio.sleep(2)
        await human_scroll(page, 500)
        await asyncio.sleep(1)
        
        js_tweets = f"""
            () => {{
                const tweets = [];
                document.querySelectorAll('[data-testid="tweet"]').forEach((tweet, index) => {{
                    if (index >= {count}) return;
                    const textEl = tweet.querySelector('[data-testid="tweetText"]');
                    const timeEl = tweet.querySelector('time');
                    const isPinned = !!tweet.querySelector('[data-testid="pinIcon"]');
                    tweets.push({{
                        text: textEl ? textEl.innerText.trim() : '',
                        time: timeEl ? timeEl.getAttribute('datetime') : '',
                        is_pinned: isPinned
                    }});
                }});
                return tweets;
            }}
        """
        
        tweets_data = await page.execute_script(js_tweets)
        
        if not tweets_data:
            await send_message_safe(update, f"❌ Твиты @{username} не найдены")
            return
        
        response = f"📊 **ТВИТЫ @{username}**\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n📌 {len(tweets_data)}\n\n"
        for i, tweet in enumerate(tweets_data[:5], 1):
            response += f"**{i}.** {tweet.get('text', '')[:200]}\n"
            if tweet.get('is_pinned'):
                response += "📌 ЗАКРЕПЛЕН\n"
            response += "\n"
        
        if len(response) > 4000:
            filename = f"tweets_{username}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(str(tweets_data))
            await update.message.reply_document(document=open(filename, 'rb'))
        else:
            await send_message_safe(update, response)
        
    except Exception as e:
        await send_message_safe(update, f"❌ Ошибка: {str(e)[:200]}")

async def setcookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🍪 **Обновление кук**\n\n"
        "Отправьте JSON:\n"
        "`[{\"name\":\"auth_token\",\"value\":\"...\",\"domain\":\".x.com\"}]`",
        parse_mode='Markdown'
    )
    context.user_data['waiting_for_cookies'] = True

async def handle_cookies_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global COOKIES
    if not context.user_data.get('waiting_for_cookies'):
        return
    
    try:
        data = json.loads(update.message.text)
        new_cookies = []
        if isinstance(data, list):
            for cookie in data:
                if 'name' in cookie and 'value' in cookie:
                    new_cookies.append({
                        "name": cookie['name'],
                        "value": cookie['value'],
                        "domain": cookie.get('domain', '.x.com'),
                        "path": cookie.get('path', '/')
                    })
        if new_cookies:
            COOKIES = new_cookies
            context.user_data['waiting_for_cookies'] = False
            await close_pydoll_browser()
            await update.message.reply_text(f"✅ Обновлено {len(COOKIES)} кук")
    except:
        pass

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['waiting_for_cookies'] = False
    await update.message.reply_text("✅ Отменено")

# ========== ЗАПУСК ==========

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("tweets", tweets))
    app.add_handler(CommandHandler("shadow", shadow))
    app.add_handler(CommandHandler("api", api))
    app.add_handler(CommandHandler("extract", extract))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("close", close))
    app.add_handler(CommandHandler("setcookies", setcookies))
    app.add_handler(CommandHandler("cancel", cancel))
    
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookies_input))
    
    print("\n✅ Бот запущен!")
    print(f"📦 Pydoll: {'✅' if PYDOLL_AVAILABLE else '❌'}")
    print(f"📦 Pydantic: {'✅' if PYDANTIC_AVAILABLE else '❌'}")
    print(f"🌐 Chromium: {'✅' if CHROMIUM_INSTALLED else '❌'}")
    print("\nКоманды:")
    print("  /start - Главное меню")
    print("  /login - Авторизация")
    print("  /tweets <username> - Твиты")
    print("  /shadow - Shadow DOM")
    print("  /api <url> - API запрос")
    print("  /extract - Извлечение данных")
    print("  /screen - Скриншот")
    print("  /status - Статус")
    print("  /close - Закрыть браузер")
    print("  /setcookies - Обновить куки")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()