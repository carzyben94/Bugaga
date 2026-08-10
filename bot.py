
import os
import sys
import time
import logging
import asyncio
import json
import httpx
import warnings
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.helpers import escape_markdown

import dspy
from dspy import Signature, InputField, OutputField, settings, ReActV2, Tool

warnings.filterwarnings("ignore")

# ============================================================
# НАСТРОЙКА
# ============================================================

LOGS_DIR = '/app/logs'
SCREENSHOTS_DIR = '/app/screenshots'
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'bot.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("dspy").setLevel(logging.INFO)
logging.getLogger("websockets").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# ============================================================
# ПУТИ
# ============================================================

sys.path.insert(0, "browser-harness/src")

from browser_harness.helpers import (
    new_tab, goto_url, wait_for_load, page_info, capture_screenshot,
    click_at_xy, type_text, press_key, scroll, js,
    list_tabs, current_tab, close_tab, switch_tab, fill_input
)
from browser_harness.admin import ensure_daemon

# ============================================================
# DSPy АДАПТЕР ДЛЯ AGNES AI
# ============================================================

class AgnesLM(dspy.LM):
    """Адаптер для Agnes AI"""
    
    def __init__(self, model="agnes-2.0-flash", api_key=None, **kwargs):
        self.api_key = api_key or os.environ.get("AGNES_API_KEY")
        self.model = model
        
        super().__init__(
            model=model, 
            model_type="chat",
            temperature=kwargs.get("temperature", 0.3),
            max_tokens=kwargs.get("max_tokens", 2000),
            cache=False
        )
        
        self.provider = "agnes-ai"
        self.forward_contract = "legacy"
    
    def forward(self, prompt=None, messages=None, **kwargs):
        if not self.api_key:
            logger.error("❌ AGNES_API_KEY не задан")
            return ["Ошибка: API ключ не задан"]
        
        params = {**self.kwargs, **kwargs}
        
        if messages:
            api_messages = messages
        else:
            api_messages = [{"role": "user", "content": prompt or ""}]
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature": params.get("temperature", 0.3),
            "max_tokens": params.get("max_tokens", 2000)
        }
        
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    "https://apihub.agnes-ai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                
                if "choices" in data and len(data["choices"]) > 0:
                    result = data["choices"][0]["message"]["content"]
                    return [result]
                return ["Ошибка: пустой ответ от API"]
                
        except httpx.TimeoutException:
            return ["Ошибка: таймаут API (60 сек)"]
        except Exception as e:
            logger.error(f"❌ Ошибка Agnes API: {e}")
            return [f"Ошибка: {str(e)}"]
    
    def __call__(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)
    
    async def aforward(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)

# ============================================================
# СИГНАТУРА
# ============================================================

class BrowserTask(Signature):
    """Ты агент с доступом к браузеру.
    Используй инструменты для выполнения задач пользователя.
    """
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Ответ на задачу")

# ============================================================
# ИНСТРУМЕНТЫ
# ============================================================

def tool_new_tab() -> str:
    """Открыть новую вкладку"""
    try:
        new_tab()
        return "✅ Новая вкладка открыта"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_goto_url(url: str) -> str:
    """Перейти на URL и дождаться загрузки"""
    try:
        goto_url(url)
        wait_for_load()
        return f"✅ Перешел на {url}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_wait_for_load() -> str:
    """Дождаться загрузки страницы"""
    try:
        wait_for_load()
        return "✅ Страница загружена"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_js(expression: str) -> str:
    """Выполнить JavaScript на странице"""
    try:
        result = js(expression)
        if isinstance(result, dict):
            return str(result.get('result', result))
        return str(result) if result is not None else "✅ JavaScript выполнен"
    except Exception as e:
        return f"❌ Ошибка JavaScript: {e}"

def tool_capture_screenshot(filename: str = None) -> str:
    """Сделать скриншот страницы"""
    try:
        if not filename:
            timestamp = int(time.time())
            filename = f"screenshot_{timestamp}.png"
        full_path = os.path.join(SCREENSHOTS_DIR, filename)
        capture_screenshot(path=full_path)
        return f"✅ Скриншот сохранен: {filename}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_fill_input(selector: str, text: str) -> str:
    """Заполнить поле ввода по CSS селектору"""
    try:
        fill_input(selector, text)
        return f"✅ Заполнено: {selector} -> {text}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_click_at_xy(x: int, y: int) -> str:
    """Кликнуть по координатам"""
    try:
        click_at_xy(x, y)
        return f"✅ Клик по ({x}, {y})"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_type_text(text: str) -> str:
    """Ввести текст"""
    try:
        type_text(text)
        return f"✅ Введено: {text}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_press_key(key: str) -> str:
    """Нажать клавишу"""
    try:
        press_key(key)
        return f"✅ Нажата клавиша: {key}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_scroll(dx: int, dy: int) -> str:
    """Прокрутить страницу"""
    try:
        scroll(dx, dy)
        return f"✅ Прокрутка на ({dx}, {dy})"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_page_info() -> str:
    """Получить информацию о странице"""
    try:
        info = page_info()
        return f"URL: {info.get('url', 'unknown')}\nTitle: {info.get('title', 'unknown')}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_list_tabs() -> str:
    """Список всех открытых вкладок"""
    try:
        tabs = list_tabs()
        return f"Вкладки: {tabs}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_current_tab() -> str:
    """ID текущей вкладки"""
    try:
        tab = current_tab()
        return f"Текущая вкладка: {tab}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_switch_tab(tab_id: int) -> str:
    """Переключиться на вкладку по ID"""
    try:
        switch_tab(tab_id)
        return f"✅ Переключился на вкладку {tab_id}"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def tool_close_tab() -> str:
    """Закрыть текущую вкладку"""
    try:
        close_tab()
        return "✅ Вкладка закрыта"
    except Exception as e:
        return f"❌ Ошибка: {e}"

# ============================================================
# ВСЕ ИНСТРУМЕНТЫ
# ============================================================

tools = [
    Tool(tool_new_tab),
    Tool(tool_goto_url),
    Tool(tool_wait_for_load),
    Tool(tool_js),
    Tool(tool_capture_screenshot),
    Tool(tool_fill_input),
    Tool(tool_click_at_xy),
    Tool(tool_type_text),
    Tool(tool_press_key),
    Tool(tool_scroll),
    Tool(tool_page_info),
    Tool(tool_list_tabs),
    Tool(tool_current_tab),
    Tool(tool_switch_tab),
    Tool(tool_close_tab),
]

# ============================================================
# СОЗДАНИЕ АГЕНТА
# ============================================================

def create_browser_agent():
    """Создать ReActV2 агента"""
    try:
        agent = ReActV2(
            signature=BrowserTask,
            tools=tools,
            max_iters=10,
        )
        logger.info("✅ ReActV2 агент создан")
        return agent
    except Exception as e:
        logger.error(f"❌ Ошибка создания ReActV2 агента: {e}")
        return None

# ============================================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================================

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

browser_agent = None

if AGNES_API_KEY:
    try:
        lm = AgnesLM(
            api_key=AGNES_API_KEY,
            temperature=0.3,
            max_tokens=2000
        )
        
        settings.configure(lm=lm)
        logger.info("✅ DSPy настроен с AgnesLM")
        
        browser_agent = create_browser_agent()
        if browser_agent:
            logger.info("✅ BrowserAgent инициализирован")
        else:
            logger.warning("⚠️ Не удалось создать агента")
        
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации DSPy: {e}")
        browser_agent = None
else:
    logger.warning("⚠️ AGNES_API_KEY не задан, DSPy не инициализирован")

# ============================================================
# КУКИ
# ============================================================

try:
    from cookies import COOKIES
    import websockets
    
    async def set_cookies_async():
        """Установить куки через WebSocket"""
        try:
            resp = httpx.get("http://localhost:9222/json/list", timeout=5.0)
            pages = resp.json()
            if not pages:
                logger.error("❌ Нет активных вкладок")
                return False
            
            ws_url = pages[0]["webSocketDebuggerUrl"]
            
            async with websockets.connect(ws_url) as ws:
                # Устанавливаем куки
                await ws.send(json.dumps({
                    "id": 1,
                    "method": "Network.setCookies",
                    "params": {"cookies": COOKIES}
                }))
                
                response = json.loads(await ws.recv())
                
                if "error" in response:
                    logger.error(f"❌ CDP ошибка: {response['error']}")
                    return False
                
                logger.info(f"🍪 Установлено {len(COOKIES)} кук")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка установки кук: {e}")
            return False
    
    def set_cookies_global():
        """Обертка для синхронного вызова"""
        try:
            loop = asyncio.get_running_loop()
            return asyncio.run_coroutine_threadsafe(set_cookies_async(), loop).result(timeout=10)
        except RuntimeError:
            return asyncio.run(set_cookies_async())
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False

except ImportError:
    logger.warning("⚠️ websockets или cookies.py не найдены")
    COOKIES = []
    
    def set_cookies_global():
        logger.warning("⚠️ Куки не установлены (нет websockets)")
        return False

# ============================================================
# РАЗМЕР ОКНА
# ============================================================

async def set_viewport_async():
    """Установить размер окна через WebSocket"""
    try:
        resp = httpx.get("http://localhost:9222/json/list", timeout=5.0)
        pages = resp.json()
        if not pages:
            logger.warning("⚠️ Нет активных вкладок для установки размера")
            return False
        
        ws_url = pages[0]["webSocketDebuggerUrl"]
        
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({
                "id": 2,
                "method": "Emulation.setDeviceMetricsOverride",
                "params": {
                    "width": 1280,
                    "height": 720,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                    "screenWidth": 1280,
                    "screenHeight": 720,
                    "positionX": 0,
                    "positionY": 0
                }
            }))
            
            response = json.loads(await ws.recv())
            
            if "error" in response:
                logger.warning(f"⚠️ CDP ошибка: {response['error']}")
                return False
            
            logger.info("✅ Размер окна установлен: 1280x720")
            return True
            
    except Exception as e:
        logger.warning(f"⚠️ Не удалось установить размер окна: {e}")
        return False

def set_viewport_global():
    """Обертка для синхронного вызова"""
    try:
        loop = asyncio.get_running_loop()
        return asyncio.run_coroutine_threadsafe(set_viewport_async(), loop).result(timeout=10)
    except RuntimeError:
        return asyncio.run(set_viewport_async())
    except Exception as e:
        logger.warning(f"⚠️ Не удалось установить размер окна: {e}")
        return False

# ============================================================
# ЗАПУСК БРАУЗЕРА
# ============================================================

os.environ["BU_CDP_URL"] = "http://localhost:9222"

try:
    ensure_daemon()
    logger.info("✅ Браузер готов")
except Exception as e:
    logger.error(f"❌ Ошибка запуска браузера: {e}")
    sys.exit(1)

# Устанавливаем куки
if COOKIES:
    set_cookies_global()
else:
    logger.info("ℹ️ Куки не установлены (нет cookies.py)")

# Устанавливаем размер окна
set_viewport_global()

# ============================================================
# КОМАНДЫ
# ============================================================

async def start(update, context):
    await update.message.reply_text(
        "🧠 **DSPy Браузерный агент**\n\n"
        "/dspy <запрос> — выполнить задачу через агента\n"
        "/log — скачать логи\n\n"
        "📌 **Примеры:**\n"
        "/dspy открыть google.com и сделать скриншот\n"
        "/dspy найти новости о Трампе на BBC\n"
        "/dspy перейти на сайт и показать заголовки"
    )

async def log(update, context):
    try:
        log_file = os.path.join(LOGS_DIR, 'bot.log')
        if not os.path.exists(log_file):
            await update.message.reply_text("📭 Лог-файл не найден")
            return
        
        with open(log_file, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename='bot.log',
                caption=f"📋 Логи бота ({os.path.getsize(log_file)} байт)"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def dspy_command(update, context):
    """Обработчик команды /dspy"""
    if not browser_agent:
        await update.message.reply_text(
            "❌ DSPy не инициализирован.\n"
            "Проверьте AGNES_API_KEY"
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "📝 **Пример использования:**\n"
            "/dspy открыть google.com и сделать скриншот",
            parse_mode='Markdown'
        )
        return
    
    query = " ".join(context.args)
    username = update.effective_user.username or "unknown"
    logger.info(f"🧠 {username} запросил: {query}")
    
    status_msg = await update.message.reply_text("🧠 Думаю...")
    
    try:
        # Вызываем агента
        result = browser_agent(question=query)
        
        # 🔥 ПРАВИЛЬНАЯ ОБРАБОТКА ОТВЕТА
        if isinstance(result, list):
            answer = result[0] if result else "Пустой ответ"
        elif hasattr(result, 'answer'):
            answer = result.answer
        else:
            answer = str(result)
        
        if answer and answer.strip():
            answer_escaped = escape_markdown(answer[:4000], version=2)
            await status_msg.edit_text(
                f"✅ **Результат:**\n{answer_escaped}",
                parse_mode='MarkdownV2'
            )
        else:
            await status_msg.edit_text("❌ Агент вернул пустой ответ")
                
    except Exception as e:
        logger.error(f"❌ DSPy ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("log", log))
    app.add_handler(CommandHandler("dspy", dspy_command))
    
    logger.info("🚀 Бот запущен!")
    logger.info(f"🧠 DSPy статус: {'✅ Активен (ReActV2)' if browser_agent else '❌ Отключен'}")
    logger.info(f"🍪 Куки: {'✅ Установлены' if COOKIES else '❌ Не установлены'}")
    logger.info(f"📁 Логи: {LOGS_DIR}")
    logger.info(f"📸 Скриншоты: {SCREENSHOTS_DIR}")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()