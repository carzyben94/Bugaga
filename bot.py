import os
import sys
import asyncio
import logging
import subprocess
import time
import json
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================
# ДОБАВЛЯЕМ ЛОКАЛЬНЫЙ browser-harness
# ============================================

sys.path.insert(0, "browser-harness/src")

# ============================================
# ИМПОРТЫ BROWSER HARNESS (ВСЕ СИНХРОННЫЕ)
# ============================================

from browser_harness.helpers import (
    new_tab,
    goto_url,
    wait_for_load,
    close_tab,
    page_info,
    current_tab,
    capture_screenshot,
    js,
    list_tabs,
    switch_tab,
    fill_input,
    click_at_xy,
    type_text,
    press_key,
    scroll,
)
from browser_harness.admin import ensure_daemon

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не установлен!")

# ============================================
# ПРОВЕРКА КОМПОНЕНТОВ
# ============================================

def check_veil():
    try:
        import veilbrowser
        return True, getattr(veilbrowser, '__version__', 'unknown')
    except ImportError:
        return False, None

def check_chrome():
    paths = ["/usr/bin/chromium", "/usr/bin/google-chrome", "/usr/bin/chrome"]
    for p in paths:
        if os.path.exists(p):
            return p
    try:
        result = subprocess.run(['which', 'chromium'], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except:
        pass
    return None

VEIL_OK, VEIL_VER = check_veil()
CHROME_PATH = check_chrome()

# ============================================
# DSPy ИНТЕГРАЦИЯ (ЧИСТЫЙ DSPy 3.3.0b1)
# ============================================

try:
    import warnings
    import httpx
    import dspy
    from dspy import Signature, InputField, OutputField, Module, settings, ReActV2, Tool
    warnings.filterwarnings("ignore")
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False
    logger.warning("⚠️ DSPy не установлен. Установи: pip install dspy httpx")

class AgnesLM(dspy.LM):
    """Адаптер для Agnes AI совместимый с DSPy"""
    
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
                
        except Exception as e:
            logger.error(f"❌ Ошибка Agnes API: {e}")
            return [f"Ошибка: {str(e)}"]
    
    def __call__(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)
    
    async def aforward(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)


class BrowserTask(Signature):
    """
    Ты агент с доступом к браузеру через Browser Harness.
    
    ДОСТУПНЫЕ ИНСТРУМЕНТЫ BROWSER HARNESS:
    
    1. Навигация:
       - tool_new_tab(url) - открыть новую вкладку с URL
       - tool_goto_url(url) - перейти на URL
       - tool_wait_for_load() - дождаться загрузки
       - tool_close_tab() - закрыть вкладку
    
    2. Информация о странице:
       - tool_page_info() - URL и заголовок
       - tool_get_text() - весь текст на странице
       - tool_get_links() - все ссылки
       - tool_get_buttons() - все кнопки
       - tool_get_headings() - все заголовки
    
    3. Взаимодействие:
       - tool_js(expression) - выполнить JavaScript
       - tool_fill_input(selector, text) - заполнить поле
       - tool_click_at_xy(x, y) - кликнуть по координатам
       - tool_scroll(x, y) - прокрутить страницу
    
    4. Скриншоты:
       - tool_capture_screenshot(filename) - сделать скриншот
    
    ПРАВИЛА:
    - Всегда используй инструменты Browser Harness
    - Для получения текста используй tool_get_text
    - Для кликов используй tool_click_at_xy
    - Для заполнения форм используй tool_fill_input
    """
    
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Ответ с использованием Browser Harness")


def create_browser_agent(tools, max_iters=10):
    """Создать ReActV2 агента с инструментами"""
    try:
        agent = ReActV2(
            signature=BrowserTask,
            tools=tools,
            max_iters=max_iters,
        )
        logger.info("✅ ReActV2 агент создан")
        return agent
    except Exception as e:
        logger.error(f"❌ Ошибка создания агента: {e}")
        return None


def init_dspy(api_key=None, tools=None, max_iters=10):
    """Инициализировать DSPy с Agnes AI"""
    api_key = api_key or os.environ.get("AGNES_API_KEY")
    
    if not api_key:
        logger.warning("⚠️ AGNES_API_KEY не задан, DSPy не инициализирован")
        return None, None
    
    try:
        lm = AgnesLM(
            api_key=api_key,
            temperature=0.3,
            max_tokens=2000
        )
        
        settings.configure(lm=lm)
        logger.info("✅ DSPy настроен с AgnesLM")
        
        if tools:
            agent = create_browser_agent(tools, max_iters)
        else:
            agent = None
        
        return lm, agent
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации DSPy: {e}")
        return None, None


def run_agent(agent, question: str) -> str:
    """Запустить агента с вопросом"""
    if not agent:
        return "❌ Агент не инициализирован"
    
    try:
        result = agent(question=question)
        answer = getattr(result, 'answer', str(result))
        return answer if answer and answer.strip() else "❌ Агент вернул пустой ответ"
    except Exception as e:
        logger.error(f"❌ Ошибка выполнения агента: {e}")
        return f"❌ Ошибка: {str(e)}"

# ============================================
# БРАУЗЕР
# ============================================

browser_instance = None
chrome_process = None
cdp_url = "http://127.0.0.1:9222"
dspy_agent = None
dspy_lm = None

# ============================================
# ИНИЦИАЛИЗАЦИЯ DSPy С ИНСТРУМЕНТАМИ
# ============================================

def init_dspy_agent():
    """Инициализация DSPy агента с инструментами Browser Harness"""
    global dspy_agent, dspy_lm
    
    if not DSPY_AVAILABLE:
        logger.warning("⚠️ DSPy не доступен")
        return
    
    AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
    if not AGNES_API_KEY:
        logger.warning("⚠️ AGNES_API_KEY не задан, DSPy отключен")
        return
    
    try:
        # ============================================================
        # ВСЕ ИНСТРУМЕНТЫ BROWSER HARNESS ДЛЯ DSPy
        # ============================================================
        
        def tool_new_tab(url: str = "https://example.com") -> str:
            """Открыть новую вкладку с URL"""
            try:
                new_tab(url)
                wait_for_load()
                return f"✅ Открыта вкладка: {url}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_goto_url(url: str) -> str:
            """Перейти на URL"""
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
                return str(result) if result is not None else "✅ JavaScript выполнен"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_capture_screenshot(filename: str = None) -> str:
            """Сделать скриншот страницы"""
            try:
                if not filename:
                    timestamp = int(time.time())
                    filename = f"screenshot_{timestamp}.png"
                path = capture_screenshot(filename)
                return f"✅ Скриншот сохранен: {path}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_page_info() -> str:
            """Получить информацию о странице"""
            try:
                info = page_info()
                return f"URL: {info.get('url', 'unknown')}\nTitle: {info.get('title', 'unknown')}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_get_text() -> str:
            """Получить весь текст на странице"""
            try:
                result = js('document.body.innerText')
                if result and len(result) > 10:
                    return result[:5000]
                return "❌ Текст не найден"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_get_links() -> str:
            """Получить все ссылки на странице"""
            try:
                result = js('Array.from(document.querySelectorAll("a")).map(el => el.href).filter(h => h)')
                if isinstance(result, list) and result:
                    links = [str(item) for item in result if item]
                    return f"Ссылки ({len(links)}): {links[:20]}"
                return "❌ Ссылок не найдено"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_get_buttons() -> str:
            """Получить все кнопки на странице"""
            try:
                result = js('Array.from(document.querySelectorAll("button, input[type=submit]")).map(el => el.innerText || el.value || el.type).filter(t => t && t.trim())')
                if isinstance(result, list) and result:
                    buttons = [str(item).strip() for item in result if item and str(item).strip()]
                    return f"Кнопки: {buttons[:20]}"
                return "❌ Кнопок не найдено"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_get_headings() -> str:
            """Получить все заголовки на странице"""
            try:
                result = js('Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6")).map(el => `${el.tagName}: ${el.innerText}`).filter(t => t && t.trim())')
                if isinstance(result, list) and result:
                    headings = [str(item).strip() for item in result if item and str(item).strip()]
                    return "Заголовки:\n" + "\n".join(headings)
                return "❌ Заголовков не найдено"
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
        
        def tool_fill_input(selector: str, text: str) -> str:
            """Заполнить поле ввода по CSS селектору"""
            try:
                fill_input(selector, text)
                return f"✅ Заполнено: {selector}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_click_at_xy(x: int, y: int) -> str:
            """Кликнуть по координатам"""
            try:
                click_at_xy(x, y)
                return f"✅ Клик по ({x}, {y})"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_scroll(dx: int, dy: int) -> str:
            """Прокрутить страницу"""
            try:
                scroll(dx, dy)
                return f"✅ Прокрутка на ({dx}, {dy})"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        # ============================================================
        # СОБИРАЕМ ВСЕ ИНСТРУМЕНТЫ
        # ============================================================
        
        tools = [
            Tool(tool_new_tab),
            Tool(tool_goto_url),
            Tool(tool_wait_for_load),
            Tool(tool_js),
            Tool(tool_capture_screenshot),
            Tool(tool_page_info),
            Tool(tool_get_text),
            Tool(tool_get_links),
            Tool(tool_get_buttons),
            Tool(tool_get_headings),
            Tool(tool_list_tabs),
            Tool(tool_current_tab),
            Tool(tool_switch_tab),
            Tool(tool_close_tab),
            Tool(tool_fill_input),
            Tool(tool_click_at_xy),
            Tool(tool_scroll),
        ]
        
        # Инициализируем DSPy с инструментами
        dspy_lm, dspy_agent = init_dspy(
            api_key=AGNES_API_KEY,
            tools=tools,
            max_iters=10
        )
        
        if dspy_agent:
            logger.info(f"✅ DSPy агент инициализирован с {len(tools)} инструментами")
        else:
            logger.warning("⚠️ Не удалось создать DSPy агента")
            
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации DSPy: {e}")
        dspy_agent = None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ **Veil + browser-harness + DSPy**\n\n"
        "Команды:\n"
        "/start_veil - запустить Veil\n"
        "/check - проверить браузер\n"
        "/harness - тест harness\n"
        "/dspy <задача> - задать вопрос агенту\n"
        "/diag - диагностика"
    )

async def start_veil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_instance, chrome_process
    await update.message.reply_text("🔄 Запускаю Veil...")
    
    if not VEIL_OK:
        await update.message.reply_text(
            "❌ Veil не установлен!\n"
            "Установи: pip install git+https://github.com/acunningham-ship-it/veilbrowser.git#subdirectory=python"
        )
        return
    
    try:
        if not CHROME_PATH:
            await update.message.reply_text("❌ Chrome не найден!")
            return
        
        await update.message.reply_text("🔄 Запускаю Chrome с маскировкой...")
        
        chrome_process = subprocess.Popen(
            [
                CHROME_PATH,
                "--headless=new",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--remote-debugging-port=9222",
                "--use-gl=angle",
                "--use-angle=gl-egl",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                f"--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        await asyncio.sleep(2)
        
        os.environ["BU_CDP_URL"] = cdp_url
        ensure_daemon()
        logger.info("✅ Daemon browser-harness запущен")
        
        from veilbrowser import Browser
        browser_instance = await Browser.connect(cdp_url)
        
        # Инициализируем DSPy агента после запуска браузера
        if DSPY_AVAILABLE:
            await update.message.reply_text("🧠 Инициализирую DSPy агента...")
            init_dspy_agent()
        
        await update.message.reply_text(
            f"✅ **Veil запущен!**\n\n"
            f"🔌 CDP: {cdp_url}\n"
            f"🆔 PID: {chrome_process.pid}\n"
            f"🧠 DSPy: {'✅ Активен' if dspy_agent else '❌ Отключен'}\n\n"
            f"Используй /dspy <задача> для AI-агента"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def check_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Проверяю браузер...")
    
    if not browser_instance:
        await update.message.reply_text("❌ Сначала запусти Veil: /start_veil")
        return
    
    try:
        new_tab("https://bot.sannysoft.com")
        wait_for_load()
        
        screenshot_path = capture_screenshot()
        if screenshot_path and os.path.exists(screenshot_path):
            with open(screenshot_path, 'rb') as f:
                await update.message.reply_photo(photo=f, caption="📸 Проверка")
        
        result = js("""
            () => ({
                webdriver: navigator.webdriver,
                userAgent: navigator.userAgent,
                platform: navigator.platform
            })
        """)
        
        if result.get('webdriver') is False:
            verdict = "✅ **Браузер НЕОТЛИЧИМ!** 🎉"
        else:
            verdict = "⚠️ **Браузер как бот**"
        
        await update.message.reply_text(
            f"🔍 **Результат**\n\n"
            f"{verdict}\n"
            f"• webdriver: `{result.get('webdriver')}`\n"
            f"• platform: `{result.get('platform')}`"
        )
        
        close_tab()
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def test_harness(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧪 Тестирую browser-harness...")
    
    if not browser_instance:
        await update.message.reply_text("❌ Сначала запусти Veil: /start_veil")
        return
    
    try:
        report = "🧪 **Тест browser-harness helpers**\n\n"
        
        new_tab("https://example.com")
        report += "✅ new_tab()\n"
        
        wait_for_load()
        report += "✅ wait_for_load()\n"
        
        info = page_info()
        report += f"✅ page_info(): {info.get('title', 'N/A')[:30]}\n"
        
        tab = current_tab()
        report += f"✅ current_tab(): {tab.get('title', 'N/A')[:30]}\n"
        
        tabs = list_tabs()
        report += f"✅ list_tabs(): {len(tabs)} вкладок\n"
        
        ua = js("navigator.userAgent")
        report += f"✅ js(): {str(ua)[:40]}...\n"
        
        scroll(0, 100)
        report += "✅ scroll()\n"
        
        screenshot_path = capture_screenshot()
        if screenshot_path and os.path.exists(screenshot_path):
            with open(screenshot_path, 'rb') as f:
                await update.message.reply_photo(photo=f, caption="📸 Скриншот")
            report += "✅ capture_screenshot()\n"
        
        close_tab()
        report += "✅ close_tab()\n"
        
        await update.message.reply_text(report + "\n🎉 Все функции работают!")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /dspy"""
    if not context.args:
        await update.message.reply_text(
            "🧠 **DSPy Agent**\n\n"
            "Отправь задачу агенту:\n"
            "`/dspy открой google.com и сделай скриншот`\n\n"
            "Доступные инструменты:\n"
            "• new_tab / goto_url\n"
            "• get_text / get_links / get_buttons\n"
            "• fill_input / click_at_xy\n"
            "• capture_screenshot / js\n"
            "• scroll / list_tabs / close_tab"
        )
        return
    
    if not browser_instance:
        await update.message.reply_text("❌ Сначала запусти Veil: /start_veil")
        return
    
    if not DSPY_AVAILABLE:
        await update.message.reply_text(
            "❌ **DSPy не установлен!**\n\n"
            "Установи:\n"
            "```bash\n"
            "pip install dspy httpx\n"
            "```"
        )
        return
    
    if not dspy_agent:
        await update.message.reply_text(
            "❌ **DSPy агент не инициализирован!**\n\n"
            "Проверьте:\n"
            "1. Переменную AGNES_API_KEY\n"
            "2. Интернет-соединение\n\n"
            "Перезапусти бота: /start_veil"
        )
        return
    
    user_query = " ".join(context.args)
    username = update.effective_user.username or "unknown"
    logger.info(f"👤 {username} DSPy запрос: {user_query}")
    
    status_msg = await update.message.reply_text("🧠 Думаю...")
    
    try:
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(None, run_agent, dspy_agent, user_query)
        
        if not answer or answer.strip() == "":
            await status_msg.edit_text("❌ Агент вернул пустой ответ")
            return
        
        if len(answer) > 4000:
            answer = answer[:4000] + "\n\n... (обрезано)"
        
        await status_msg.edit_text(
            f"✅ **Результат:**\n\n{answer}"
        )
        
    except Exception as e:
        logger.error(f"❌ DSPy ошибка: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:300]}")

async def diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = f"📊 **Диагностика**\n\n"
    report += f"• Veil: {'✅' if VEIL_OK else '❌'} {VEIL_VER or ''}\n"
    report += f"• Chrome: {'✅' if CHROME_PATH else '❌'}\n"
    report += f"• Harness path: {'✅' if os.path.exists('browser-harness/src') else '❌'}\n"
    report += f"• Браузер: {'✅' if browser_instance else '❌'}\n"
    report += f"• DSPy: {'✅' if dspy_agent else '❌'}\n"
    report += f"• BU_CDP_URL: {os.environ.get('BU_CDP_URL', '❌')}\n"
    report += f"• AGNES_API_KEY: {'✅' if os.environ.get('AGNES_API_KEY') else '❌'}\n"
    
    if CHROME_PATH:
        report += f"• Путь Chrome: `{CHROME_PATH}`\n"
    if chrome_process:
        report += f"• PID Chrome: `{chrome_process.pid}`\n"
    
    try:
        import requests
        response = requests.get("http://127.0.0.1:9222/json/version", timeout=2)
        if response.status_code == 200:
            report += f"• CDP: ✅ Доступен\n"
        else:
            report += f"• CDP: ⚠️ Код {response.status_code}\n"
    except:
        report += "• CDP: ❌ Не доступен\n"
    
    await update.message.reply_text(report)

# ============================================
# ЗАПУСК
# ============================================

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("start_veil", start_veil))
    app.add_handler(CommandHandler("check", check_browser))
    app.add_handler(CommandHandler("harness", test_harness))
    app.add_handler(CommandHandler("dspy", dspy_command))
    app.add_handler(CommandHandler("diag", diag))
    
    logger.info("🤖 Бот запущен!")
    logger.info("📋 Команды: /start_veil, /check, /harness, /dspy, /diag")
    app.run_polling()

if __name__ == "__main__":
    main()