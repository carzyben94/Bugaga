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
# КУКИ ДЛЯ X.COM (TWITTER)
# ============================================

COOKIES = [
    {
        "name": "__cuid",
        "value": "55d2d7c5-4888-430a-b024-dd785da46ef4",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "personalization_id",
        "value": "\"v1_VL5PDSWqcwv7LNBV75SiLA==\"",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "g_state",
        "value": "{\"i_l\":0,\"i_ll\":1786493441069,\"i_b\":\"GK5KqYSRaGCT7CvSxBv3wqY6m7ne53iSPqkYW+ROGIo\",\"i_e\":{\"enable_itp_optimization\":24},\"i_et\":1786493441069}",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "lang",
        "value": "ru",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "dnt",
        "value": "1",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "gt",
        "value": "2087858962263671253",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "guest_id",
        "value": "v1%3A178661934178349765",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "twid",
        "value": "u%3D2075158859295997952",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "auth_token",
        "value": "c67259d770166a76598c693d9536c5356f521343",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "guest_id_ads",
        "value": "v1%3A178661934178349765",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "guest_id_marketing",
        "value": "v1%3A178661934178349765",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "ct0",
        "value": "a7588aaf794885b9e039dc7b81874e17e2786d50a7ba5794412780256f819111535e58b52f13fd571176e7b3d3ceb79a95aa722288c8811a4cfb02ff4a9ecf2f36e0ab11032d6aab77df44902a0d2715",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "__cf_bm",
        "value": ".WtFBy2_JUO1VAFxh4adk0Ke7.8T0w0MZNBftx1Y7Og-1786619407.2810972-1.0.1.1-V7njqiTJRq5SKwLgiqsE6SGR1qScNXtusMEP1ii5Ai24nxQMM76kNpVeVXYPE4zyY4gLtQKmQCdFCgdsuocz2NxkGJq.ku2bfEopXW73Ywm6wVrXxc0LnxPRWbV.vXZI",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    }
]

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
# УНИВЕРСАЛЬНАЯ ОЧИСТКА ВКЛАДОК (БЕЗ СООБЩЕНИЙ В TELEGRAM)
# ============================================

def cleanup_tabs(keep_one=True):
    """
    Закрывает все вкладки, кроме одной (по умолчанию).
    Если keep_one=True - оставляет одну чистую вкладку.
    Без сообщений в Telegram, только логи.
    """
    try:
        tabs = list_tabs()
        if not tabs:
            logger.info("ℹ️ Нет открытых вкладок")
            return
        
        logger.info(f"🧹 Очистка: {len(tabs)} вкладок")
        
        # Если нужно оставить одну вкладку
        if keep_one and len(tabs) > 1:
            # Закрываем все, кроме первой
            for i, tab in enumerate(tabs):
                if i == 0:
                    continue
                try:
                    switch_tab(tab)
                    close_tab()
                    logger.info(f"✅ Закрыта вкладка: {tab}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось закрыть {tab}: {e}")
            
            # Переключаемся на первую вкладку
            try:
                switch_tab(tabs[0])
                goto_url("about:blank")
                wait_for_load()
                logger.info("✅ Оставлена одна чистая вкладка")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось переключиться: {e}")
        
        # Если keep_one=False - закрываем все
        else:
            for tab in tabs:
                try:
                    switch_tab(tab)
                    close_tab()
                    logger.info(f"✅ Закрыта вкладка: {tab}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось закрыть {tab}: {e}")
            
            new_tab("about:blank")
            wait_for_load()
            logger.info("✅ Все вкладки закрыты, создана новая")
            
    except Exception as e:
        logger.error(f"❌ Ошибка очистки: {e}")

def set_cookies_via_js():
    """Установить куки через JavaScript (наиболее надёжный способ)"""
    try:
        # Открываем страницу X.com (куки привязываются к домену)
        new_tab("https://x.com")
        wait_for_load()
        
        # Формируем JavaScript для установки всех кук
        js_code = """
        (function() {
            const cookies = %s;
            let success = 0;
            let failed = 0;
            let errors = [];
            
            cookies.forEach(function(cookie) {
                try {
                    let cookieString = cookie.name + '=' + cookie.value;
                    if (cookie.domain) cookieString += '; domain=' + cookie.domain;
                    if (cookie.path) cookieString += '; path=' + cookie.path;
                    if (cookie.secure) cookieString += '; secure';
                    if (cookie.sameSite && cookie.sameSite !== 'unspecified') {
                        cookieString += '; SameSite=' + cookie.sameSite;
                    }
                    document.cookie = cookieString;
                    success++;
                } catch(e) {
                    failed++;
                    errors.push(cookie.name + ': ' + e.message);
                }
            });
            
            return {
                success: success, 
                failed: failed, 
                errors: errors,
                total: cookies.length
            };
        })()
        """ % json.dumps(COOKIES)
        
        result = js(js_code)
        
        if result and result.get('success', 0) > 0:
            logger.info(f"✅ Установлено кук: {result.get('success')} из {result.get('total')}")
            if result.get('failed', 0) > 0:
                logger.warning(f"⚠️ Не удалось установить: {result.get('errors', [])}")
            return result.get('success', 0) > 0
        else:
            logger.error(f"❌ Не удалось установить куки: {result}")
            return False
        
    except Exception as e:
        logger.error(f"❌ Ошибка установки кук через JS: {e}")
        return False

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
        
        # 6. Куки для X.com
        def tool_set_x_cookies() -> str:
            """Установить куки для X.com (авторизация)"""
            try:
                success = set_cookies_via_js()
                if success:
                    return "✅ Куки X.com установлены"
                return "❌ Ошибка установки кук"
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
            Tool(tool_set_x_cookies),
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
        "🛡️ **Veil + browser-harness + X.com**\n\n"
        "Команды:\n"
        "/start_veil - запустить Veil с куками X.com\n"
        "/check - проверить маскировку\n"
        "/checkxcom - проверить авторизацию на X.com\n"
        "/screen <url> - сделать скриншот страницы\n"
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
        
        # Очистка без сообщения в Telegram
        cleanup_tabs(keep_one=True)
        
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
        
        # УСТАНАВЛИВАЕМ КУКИ X.COM ЧЕРЕЗ JS
        await update.message.reply_text("🍪 Устанавливаю куки X.com...")
        success = set_cookies_via_js()
        if success:
            await update.message.reply_text(f"✅ Установлены куки X.com!")
        else:
            await update.message.reply_text("⚠️ Не удалось установить куки")
        
        # Инициализируем DSPy агента
        if DSPY_AVAILABLE:
            await update.message.reply_text("🧠 Инициализирую DSPy агента...")
            init_dspy_agent()
        
        # Открываем тестовую страницу
        new_tab("https://x.com")
        wait_for_load()
        
        await update.message.reply_text(
            f"✅ **Veil запущен!**\n\n"
            f"🔌 CDP: {cdp_url}\n"
            f"🆔 PID: {chrome_process.pid}\n"
            f"🍪 Куки X.com: {'✅' if success else '❌'}\n"
            f"🧠 DSPy: {'✅ Активен' if dspy_agent else '❌ Отключен'}\n\n"
            f"📋 Команды:\n"
            f"/checkxcom - проверить авторизацию на X.com\n"
            f"/screen <url> - сделать скриншот\n"
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
                await update.message.reply_photo(photo=f, caption="📸 Проверка маскировки")
        
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
        cleanup_tabs(keep_one=True)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def check_xcom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет авторизацию на X.com через куки"""
    await update.message.reply_text("🔍 Проверяю X.com...")
    
    if not browser_instance:
        await update.message.reply_text("❌ Сначала запусти Veil: /start_veil")
        return
    
    try:
        # Открываем новую вкладку с X.com
        new_tab("https://x.com")
        wait_for_load()
        
        # Делаем скриншот
        screenshot_path = capture_screenshot()
        if screenshot_path and os.path.exists(screenshot_path):
            with open(screenshot_path, 'rb') as f:
                await update.message.reply_photo(photo=f, caption="📸 X.com после загрузки")
        
        # Проверяем, авторизованы ли мы
        result = js("""
            () => {
                // Проверяем наличие элементов
                const signUp = document.querySelector('[data-testid="signUpButton"]');
                const logIn = document.querySelector('[data-testid="loginButton"]');
                const profile = document.querySelector('[data-testid="AppTabBar_Profile_Link"]');
                const home = document.querySelector('[data-testid="AppTabBar_Home_Link"]');
                
                // Проверяем куки
                const hasAuth = document.cookie.includes('auth_token');
                const hasTwid = document.cookie.includes('twid');
                
                return {
                    hasAuthToken: hasAuth,
                    hasTwid: hasTwid,
                    hasSignUp: !!signUp,
                    hasLogIn: !!logIn,
                    hasProfile: !!profile,
                    hasHome: !!home,
                    title: document.title,
                    url: window.location.href
                };
            }
        """)
        
        # Формируем отчет
        report = "🔍 **Проверка X.com**\n\n"
        
        # Куки
        report += "🍪 **Куки:**\n"
        report += f"• auth_token: {'✅' if result.get('hasAuthToken') else '❌'}\n"
        report += f"• twid: {'✅' if result.get('hasTwid') else '❌'}\n\n"
        
        # UI элементы
        report += "🖥️ **UI элементы:**\n"
        report += f"• Кнопка 'Sign up': {'❌' if result.get('hasSignUp') else '✅ (скрыта)'}\n"
        report += f"• Кнопка 'Log in': {'❌' if result.get('hasLogIn') else '✅ (скрыта)'}\n"
        report += f"• Профиль: {'✅' if result.get('hasProfile') else '❌'}\n"
        report += f"• Домой: {'✅' if result.get('hasHome') else '❌'}\n\n"
        
        # Статус авторизации
        report += "**📊 Статус:**\n"
        if result.get('hasProfile') or result.get('hasHome'):
            report += "✅ **АВТОРИЗОВАН!** Вы вошли в X.com\n"
        elif result.get('hasSignUp') or result.get('hasLogIn'):
            report += "⚠️ **НЕ АВТОРИЗОВАН!** Куки не работают или истекли\n"
        else:
            report += "❓ **НЕИЗВЕСТНО** - страница загрузилась, но статус не определен\n"
        
        report += f"\n📌 Title: {result.get('title', 'N/A')[:100]}"
        
        await update.message.reply_text(report)
        
        close_tab()
        cleanup_tabs(keep_one=True)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def screen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /screen [url] - сделать скриншот указанного URL"""
    # Проверяем, передан ли URL
    if not context.args:
        await update.message.reply_text(
            "❌ **Укажи URL!**\n\n"
            "Пример: `/screen https://example.com`",
            parse_mode='Markdown'
        )
        return
    
    url = context.args[0]
    
    # Проверяем, что URL начинается с http:// или https://
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    await update.message.reply_text(f"🔄 Открываю `{url}` и делаю скриншот...", parse_mode='Markdown')
    
    if not browser_instance:
        await update.message.reply_text("❌ Сначала запусти Veil: /start_veil")
        return
    
    try:
        # Открываем новую вкладку с указанным URL
        new_tab(url)
        wait_for_load()
        
        # Делаем скриншот
        timestamp = int(time.time())
        filename = f"screenshot_{timestamp}.png"
        screenshot_path = capture_screenshot(filename)
        
        if screenshot_path and os.path.exists(screenshot_path):
            with open(screenshot_path, 'rb') as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=f"📸 **Скриншот:** `{url}`"
                )
            
            # Получаем информацию о странице
            info = page_info()
            await update.message.reply_text(
                f"✅ **Готово!**\n\n"
                f"📌 **Title:** {info.get('title', 'N/A')[:100]}\n"
                f"🔗 **URL:** {info.get('url', url)}"
            )
        else:
            await update.message.reply_text("❌ Не удалось сохранить скриншот")
        
        close_tab()
        cleanup_tabs(keep_one=True)
        
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
        cleanup_tabs(keep_one=True)
        
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
            "• tool_js - fallback для сложных случаев\n"
            "• tool_set_x_cookies - установить куки X.com\n\n"
            "Примеры:\n"
            "/dspy открой x.com и покажи заголовок\n"
            "/dspy установи куки X.com и открой страницу"
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
        
        # ✅ ОЧИСТКА БЕЗ СООБЩЕНИЯ В TELEGRAM (только в логах)
        cleanup_tabs(keep_one=True)
        
    except Exception as e:
        logger.error(f"❌ DSPy ошибка: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:300]}")
        
        # ✅ ДАЖЕ ПРИ ОШИБКЕ - ОЧИСТКА БЕЗ СООБЩЕНИЯ
        cleanup_tabs(keep_one=True)

async def diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = f"📊 **Диагностика**\n\n"
    report += f"• Veil: {'✅' if VEIL_OK else '❌'} {VEIL_VER or ''}\n"
    report += f"• Chrome: {'✅' if CHROME_PATH else '❌'}\n"
    report += f"• Harness path: {'✅' if os.path.exists('browser-harness/src') else '❌'}\n"
    report += f"• Браузер: {'✅' if browser_instance else '❌'}\n"
    report += f"• DSPy: {'✅' if dspy_agent else '❌'}\n"
    report += f"• BU_CDP_URL: {os.environ.get('BU_CDP_URL', '❌')}\n"
    report += f"• AGNES_API_KEY: {'✅' if os.environ.get('AGNES_API_KEY') else '❌'}\n"
    report += f"• Куки X.com: {'✅' if COOKIES else '❌'} ({len(COOKIES)} шт.)\n"
    
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
    app.add_handler(CommandHandler("checkxcom", check_xcom))
    app.add_handler(CommandHandler("screen", screen_command))
    app.add_handler(CommandHandler("harness", test_harness))
    app.add_handler(CommandHandler("ax", ax_command))
    app.add_handler(CommandHandler("dspy", dspy_command))
    app.add_handler(CommandHandler("diag", diag))
    
    logger.info("🤖 Бот запущен (по документации browser-harness)!")
    logger.info("📋 Команды: /start_veil, /check, /checkxcom, /screen, /harness, /ax, /dspy, /diag")
    logger.info(f"🍪 Загружено {len(COOKIES)} кук X.com")
    app.run_polling()

if __name__ == "__main__":
    main()