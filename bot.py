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
# ИМПОРТЫ BROWSER HARNESS (ПО ДОКУМЕНТАЦИИ)
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
    cdp,
    ensure_real_tab,
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
# ПОМОЩНИКИ ДЛЯ РАБОТЫ С ACCESSIBILITY TREE (ПО ДОКЕ)
# ============================================

def get_ax_tree():
    """
    Получить полное Accessibility Tree страницы.
    Строго по документации: cdp("Accessibility.getFullAXTree")["nodes"]
    """
    try:
        result = cdp("Accessibility.getFullAXTree")
        return result.get("nodes", [])
    except Exception as e:
        logger.error(f"❌ Ошибка получения AX Tree: {e}")
        return []

def find_element_by_role(nodes, role, name=None):
    """
    Найти элемент по роли и имени в AX Tree.
    Возвращает узел с backendDOMNodeId.
    """
    for node in nodes:
        if node.get("role") == role:
            if name is None or node.get("name") == name:
                return node
    return None

def get_element_coords(backend_node_id):
    """
    Получить координаты центра элемента по backendDOMNodeId.
    Строго по документации: cdp("DOM.getBoxModel", backendNodeId=n)["model"]["content"]
    """
    try:
        result = cdp("DOM.getBoxModel", backendNodeId=backend_node_id)
        if result and "model" in result and "content" in result["model"]:
            box = result["model"]["content"]
            # content = [x1, y1, x2, y2, x3, y3, x4, y4]
            x = sum(box[0::2]) / 4
            y = sum(box[1::2]) / 4
            return x, y
    except Exception as e:
        logger.error(f"❌ Ошибка получения координат: {e}")
    return None, None

def click_element_by_role(role, name=None):
    """
    Найти элемент по роли/имени и кликнуть по его центру.
    """
    nodes = get_ax_tree()
    target = find_element_by_role(nodes, role, name)
    if not target:
        logger.warning(f"⚠️ Элемент не найден: role={role}, name={name}")
        return False
    
    backend_id = target.get("backendDOMNodeId")
    if not backend_id:
        logger.warning("⚠️ Нет backendDOMNodeId")
        return False
    
    x, y = get_element_coords(backend_id)
    if x is None or y is None:
        return False
    
    click_at_xy(x, y)
    logger.info(f"✅ Клик по {role}:{name} at ({x:.0f}, {y:.0f})")
    return True

def get_text_from_ax_tree():
    """
    Получить текст из Accessibility Tree.
    Собирает все текстовые узлы с их ролью.
    """
    nodes = get_ax_tree()
    result = []
    for node in nodes:
        role = node.get("role", "unknown")
        name = node.get("name", "")
        if name:
            result.append(f"[{role}] {name}")
    return "\n".join(result) if result else "Нет текста в AX Tree"

# ============================================
# DSPy ИНТЕГРАЦИЯ
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
    Работай строго по документации browser-harness.
    
    ДОСТУПНЫЕ ИНСТРУМЕНТЫ:
    
    1. Навигация:
       - tool_new_tab(url) -> str — ПЕРВАЯ НАВИГАЦИЯ ТОЛЬКО ЧЕРЕЗ НЕЁ!
       - tool_goto_url(url) -> str — для навигации в активной вкладке
       - tool_wait_for_load() -> str — ВСЕГДА после навигации
       - tool_ensure_real_tab() -> str — если вкладка устарела
    
    2. Поиск элементов (РЕКОМЕНДУЕМЫЙ СПОСОБ):
       - tool_get_ax_tree() -> str — всё дерево с role, name, backendDOMNodeId
       - tool_click_by_role(role, name) -> str — клик по центру элемента
       - tool_click_by_coords(x, y) -> str — клик по координатам
       - tool_get_coords_by_role(role, name) -> str — координаты элемента
    
    3. Информация о странице:
       - tool_page_info() -> str — URL, title, viewport
       - tool_capture_screenshot() -> str — ТОЛЬКО ДЛЯ ПРОВЕРКИ
    
    4. Fallback (когда AX Tree не помогает):
       - tool_js(expression) -> str — выполнить JavaScript (canvas, виджеты)
       - tool_fill_input(selector, text) -> str — заполнить поле
       - tool_scroll(dx, dy) -> str — прокрутить страницу
    
    5. Управление вкладками:
       - tool_list_tabs() -> str
       - tool_current_tab() -> str
       - tool_switch_tab(tab_id) -> str
       - tool_close_tab() -> str
    
    ПРАВИЛА ИЗ ДОКУМЕНТАЦИИ:
    1. Первая навигация — ТОЛЬКО tool_new_tab(url), НЕ tool_goto_url(url)
    2. Всегда вызывай tool_wait_for_load() после любой навигации
    3. Для поиска используй tool_get_ax_tree(), НЕ скриншоты
    4. Для кликов — tool_click_by_role() или tool_click_by_coords()
    5. Скриншоты — только для проверки результата
    6. Если AX Tree не хватает — используй tool_js() как fallback
    7. Если вкладка устарела — tool_ensure_real_tab()
    
    СТРАТЕГИЯ ПО УМОЛЧАНИЮ:
    1. tool_new_tab(url) — открыть страницу
    2. tool_wait_for_load() — дождаться загрузки
    3. tool_get_ax_tree() — получить структуру страницы
    4. Найти элемент по role/name в AX Tree
    5. tool_click_by_role(role, name) — кликнуть
    6. tool_capture_screenshot() — проверить результат
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
# ИНИЦИАЛИЗАЦИЯ DSPy С ИНСТРУМЕНТАМИ (ПО ДОКЕ)
# ============================================

def init_dspy_agent():
    """Инициализация DSPy агента с инструментами Browser Harness по документации"""
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
        # ВСЕ ИНСТРУМЕНТЫ ПО ДОКУМЕНТАЦИИ
        # ============================================================
        
        # 1. Навигация
        def tool_new_tab(url: str = "https://example.com") -> str:
            """Открыть новую вкладку с URL (ПЕРВАЯ НАВИГАЦИЯ ТОЛЬКО ЧЕРЕЗ НЕЁ)"""
            try:
                new_tab(url)
                wait_for_load()
                return f"✅ Открыта вкладка: {url}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_goto_url(url: str) -> str:
            """Перейти на URL (для навигации в активной вкладке)"""
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
        
        def tool_ensure_real_tab() -> str:
            """Восстановить вкладку, если она устарела"""
            try:
                ensure_real_tab()
                return "✅ Вкладка восстановлена"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        # 2. Accessibility Tree (РЕКОМЕНДУЕМЫЙ СПОСОБ)
        def tool_get_ax_tree() -> str:
            """Получить Accessibility Tree страницы (role, name, backendDOMNodeId)"""
            try:
                nodes = get_ax_tree()
                if not nodes:
                    return "❌ AX Tree пуст"
                result = []
                for node in nodes[:50]:  # Ограничиваем для LLM
                    role = node.get("role", "unknown")
                    name = node.get("name", "")
                    if name:
                        result.append(f"[{role}] {name}")
                return "\n".join(result) if result else "Нет текста в AX Tree"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_click_by_role(role: str, name: str = None) -> str:
            """Кликнуть по элементу по его роли и имени"""
            try:
                success = click_element_by_role(role, name)
                if success:
                    return f"✅ Клик по {role}: {name or 'без имени'}"
                return f"❌ Элемент не найден: {role}: {name or 'без имени'}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_click_by_coords(x: int, y: int) -> str:
            """Кликнуть по координатам"""
            try:
                click_at_xy(x, y)
                return f"✅ Клик по ({x}, {y})"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_get_coords_by_role(role: str, name: str = None) -> str:
            """Получить координаты элемента по роли и имени"""
            try:
                nodes = get_ax_tree()
                target = find_element_by_role(nodes, role, name)
                if not target:
                    return f"❌ Элемент не найден: {role}: {name or 'без имени'}"
                backend_id = target.get("backendDOMNodeId")
                if not backend_id:
                    return "❌ Нет backendDOMNodeId"
                x, y = get_element_coords(backend_id)
                if x is None or y is None:
                    return "❌ Не удалось получить координаты"
                return f"Координаты: ({x:.0f}, {y:.0f})"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        # 3. Информация о странице
        def tool_page_info() -> str:
            """Получить информацию о странице (URL, title, viewport)"""
            try:
                info = page_info()
                return f"URL: {info.get('url', 'unknown')}\nTitle: {info.get('title', 'unknown')}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_capture_screenshot(filename: str = None) -> str:
            """Сделать скриншот страницы (ТОЛЬКО ДЛЯ ПРОВЕРКИ)"""
            try:
                if not filename:
                    timestamp = int(time.time())
                    filename = f"screenshot_{timestamp}.png"
                path = capture_screenshot(filename)
                return f"✅ Скриншот сохранен: {path}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        # 4. Fallback (когда AX Tree не помогает)
        def tool_js(expression: str) -> str:
            """Выполнить JavaScript на странице (fallback)"""
            try:
                result = js(expression)
                return str(result) if result is not None else "✅ JS выполнен"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_fill_input(selector: str, text: str) -> str:
            """Заполнить поле ввода по CSS селектору"""
            try:
                fill_input(selector, text)
                return f"✅ Заполнено: {selector}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_scroll(dx: int, dy: int) -> str:
            """Прокрутить страницу"""
            try:
                scroll(dx, dy)
                return f"✅ Прокрутка на ({dx}, {dy})"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        # 5. Управление вкладками
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
        # СОБИРАЕМ ВСЕ ИНСТРУМЕНТЫ
        # ============================================================
        
        tools = [
            Tool(tool_new_tab),
            Tool(tool_goto_url),
            Tool(tool_wait_for_load),
            Tool(tool_ensure_real_tab),
            Tool(tool_get_ax_tree),
            Tool(tool_click_by_role),
            Tool(tool_click_by_coords),
            Tool(tool_get_coords_by_role),
            Tool(tool_page_info),
            Tool(tool_capture_screenshot),
            Tool(tool_js),
            Tool(tool_fill_input),
            Tool(tool_scroll),
            Tool(tool_list_tabs),
            Tool(tool_current_tab),
            Tool(tool_switch_tab),
            Tool(tool_close_tab),
        ]
        
        # Инициализируем DSPy с инструментами
        dspy_lm, dspy_agent = init_dspy(
            api_key=AGNES_API_KEY,
            tools=tools,
            max_iters=10
        )
        
        if dspy_agent:
            logger.info(f"✅ DSPy агент инициализирован с {len(tools)} инструментами (по документации)")
        else:
            logger.warning("⚠️ Не удалось создать DSPy агента")
            
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации DSPy: {e}")
        dspy_agent = None

# ============================================
# TELEGRAM КОМАНДЫ
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ **Veil + browser-harness (по документации)**\n\n"
        "Команды:\n"
        "/start_veil - запустить Veil\n"
        "/check - проверить браузер\n"
        "/harness - тест harness\n"
        "/ax - показать Accessibility Tree\n"
        "/dspy <задача> - задать вопрос агенту\n"
        "/diag - диагностика"
    )

async def ax_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать Accessibility Tree страницы"""
    await update.message.reply_text("🌳 Получаю Accessibility Tree...")
    
    if not browser_instance:
        await update.message.reply_text("❌ Сначала запусти Veil: /start_veil")
        return
    
    try:
        text = get_text_from_ax_tree()
        if text and len(text) > 4000:
            text = text[:4000] + "\n\n... (обрезано)"
        await update.message.reply_text(
            f"🌳 **Accessibility Tree**\n\n{text}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def start_veil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_instance, chrome_process
    await update.message.reply_text("🔄 Запускаю Veil...")
    
    if not VEIL_OK:
        await update.message.reply_text("❌ Veil не установлен!")
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
        
        # Инициализируем DSPy агента
        if DSPY_AVAILABLE:
            await update.message.reply_text("🧠 Инициализирую DSPy агента...")
            init_dspy_agent()
        
        # Открываем тестовую страницу
        new_tab("https://example.com")
        wait_for_load()
        
        await update.message.reply_text(
            f"✅ **Veil запущен!**\n\n"
            f"🔌 CDP: {cdp_url}\n"
            f"🆔 PID: {chrome_process.pid}\n"
            f"🧠 DSPy: {'✅ Активен' if dspy_agent else '❌ Отключен'}\n\n"
            f"📋 Команды:\n"
            f"/ax - показать Accessibility Tree\n"
            f"/dspy <задача> - AI-агент"
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
        
        webdriver = result.get('webdriver')
        if webdriver in (False, None):
            verdict = "✅ **Браузер НЕОТЛИЧИМ!** 🎉"
        else:
            verdict = "⚠️ **Браузер как бот**"
        
        await update.message.reply_text(
            f"🔍 **Результат**\n\n"
            f"{verdict}\n"
            f"• webdriver: `{webdriver}`\n"
            f"• platform: `{result.get('platform')}`\n\n"
            f"💡 `None` или `false` — идеально!"
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
        report = "🧪 **Тест browser-harness (по документации)**\n\n"
        
        new_tab("https://example.com")
        report += "✅ new_tab()\n"
        
        wait_for_load()
        report += "✅ wait_for_load()\n"
        
        # 1. AX Tree
        ax = get_text_from_ax_tree()
        report += f"✅ AX Tree: {len(ax)} символов\n"
        
        # 2. Координатный клик
        nodes = get_ax_tree()
        link = find_element_by_role(nodes, "link", "More information...")
        if link:
            x, y = get_element_coords(link.get("backendDOMNodeId"))
            click_at_xy(x, y)
            report += f"✅ Клик по ссылке 'More information...'\n"
        else:
            report += "ℹ️ Ссылка 'More information...' не найдена\n"
        
        screenshot_path = capture_screenshot()
        if screenshot_path and os.path.exists(screenshot_path):
            with open(screenshot_path, 'rb') as f:
                await update.message.reply_photo(photo=f, caption="📸 После клика")
            report += "✅ capture_screenshot()\n"
        
        close_tab()
        report += "✅ close_tab()\n"
        
        await update.message.reply_text(report + "\n🎉 Все функции работают по документации!")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /dspy"""
    if not context.args:
        await update.message.reply_text(
            "🧠 **DSPy Agent (по документации browser-harness)**\n\n"
            "Доступные инструменты:\n"
            "• tool_new_tab / tool_goto_url\n"
            "• tool_get_ax_tree - Accessibility Tree (РЕКОМЕНДУЕТСЯ)\n"
            "• tool_click_by_role / tool_click_by_coords\n"
            "• tool_capture_screenshot - для проверки\n"
            "• tool_js - fallback для сложных случаев\n\n"
            "Примеры:\n"
            "/dspy открой example.com и покажи заголовок\n"
            "/dspy найди кнопку Login и кликни на неё\n"
            "/dspy сделай скриншот google.com"
        )
        return
    
    if not browser_instance:
        await update.message.reply_text("❌ Сначала запусти Veil: /start_veil")
        return
    
    if not DSPY_AVAILABLE:
        await update.message.reply_text("❌ DSPy не установлен!\nУстанови: pip install dspy httpx")
        return
    
    if not dspy_agent:
        await update.message.reply_text(
            "❌ DSPy агент не инициализирован!\n\n"
            "Проверьте:\n"
            "1. Переменную AGNES_API_KEY\n"
            "2. Перезапустите /start_veil"
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
        
        await status_msg.edit_text(f"✅ **Результат:**\n\n{answer}")
        
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
            report += f"• CDP: ⚠️ {response.status_code}\n"
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
    app.add_handler(CommandHandler("ax", ax_command))
    app.add_handler(CommandHandler("dspy", dspy_command))
    app.add_handler(CommandHandler("diag", diag))
    
    logger.info("🤖 Бот запущен (по документации browser-harness)!")
    logger.info("📋 Команды: /start_veil, /check, /harness, /ax, /dspy, /diag")
    app.run_polling()

if __name__ == "__main__":
    main()