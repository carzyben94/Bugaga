"""
dspy.py - DSPy агент + инструменты
"""

import os
import threading
import asyncio
import logging
from typing import Optional

import httpx
import dspy as dspy_lib  # ← ИМПОРТИРУЕМ КАК dspy_lib
from dspy_lib import Signature, InputField, OutputField, Tool

try:
    from dspy_lib import ReActV2
    REACT_V2_AVAILABLE = True
except ImportError:
    ReActV2 = None
    REACT_V2_AVAILABLE = False

from browser import (
    browser_goto,
    browser_back,
    browser_forward,
    browser_reload,
    browser_page_info,
    browser_inspect,
    browser_get_text,
    browser_get_html,
    browser_get_links,
    browser_click,
    browser_click_text,
    browser_click_role,
    browser_fill,
    browser_fill_label,
    browser_fill_placeholder,
    browser_type,
    browser_press,
    browser_key,
    browser_wait,
    browser_wait_selector,
    browser_select,
    browser_check,
    browser_uncheck,
    browser_hover,
    browser_attribute,
    browser_count,
    browser_js,
    browser_screenshot,
    browser_content,
)

logger = logging.getLogger(__name__)

# ============================================================
# GLOBAL STATE
# ============================================================

dspy_agent_instance = None
main_event_loop = None
agent_lock = threading.Lock()

# ============================================================
# AGNES LM
# ============================================================

class AgnesLM(dspy_lib.LM):  # ← dspy_lib.LM

    def __init__(
        self,
        model="agnes-2.0-flash",
        api_key=None,
        **kwargs,
    ):
        self.api_key = api_key or os.environ.get("AGNES_API_KEY")
        self.model = model
        self.temperature = kwargs.get("temperature", 0.2)
        self.max_tokens = kwargs.get("max_tokens", 4000)

        super().__init__(
            model=model,
            model_type="chat",
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            cache=False,
        )

        self.provider = "agnes-ai"

    def forward(self, prompt=None, messages=None, **kwargs):
        if not self.api_key:
            raise RuntimeError("AGNES_API_KEY не задан")

        params = {**self.kwargs, **kwargs}

        api_messages = messages or [
            {"role": "user", "content": prompt or ""}
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature": params.get("temperature", self.temperature),
            "max_tokens": params.get("max_tokens", self.max_tokens),
        }

        if params.get("tools"):
            payload["tools"] = params["tools"]

        if params.get("tool_choice"):
            payload["tool_choice"] = params["tool_choice"]

        try:
            with httpx.Client(
                timeout=httpx.Timeout(
                    connect=30,
                    read=120,
                    write=120,
                    pool=30,
                )
            ) as client:
                response = client.post(
                    "https://apihub.agnes-ai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

        except httpx.HTTPStatusError as e:
            body = e.response.text[:2000]
            logger.error(
                "Agnes HTTP %s: %s",
                e.response.status_code,
                body,
            )
            raise RuntimeError(
                f"Agnes HTTP {e.response.status_code}: {body}"
            ) from e

        except Exception as e:
            logger.exception("Agnes API")
            raise RuntimeError(f"Agnes API error: {e}") from e

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"Agnes вернул пустой ответ: {data}")

        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        return [content]

    def __call__(self, prompt=None, messages=None, **kwargs):
        return self.forward(
            prompt=prompt,
            messages=messages,
            **kwargs,
        )

# ============================================================
# DSPY SIGNATURE
# ============================================================

class BrowserTask(Signature):
    """
    Автономный браузерный агент.

    Стратегия Inspector 2.0:

    1. Если дан URL — tool_goto.
    2. Для неизвестной страницы сначала tool_inspect_page(mode="map").
    3. Map используй для выбора нужного элемента.
    4. Если нужна точность — tool_inspect_page(mode="full").
    5. Предпочитай semantic locators.
    6. Не кликай disabled/invisible/covered элементы.
    7. После значимого действия проверяй новое состояние.
    8. Если locator не сработал — не повторяй бесконечно,
       сначала повторный inspect.
    9. Учитывай frame index и Shadow DOM.
    10. Для SPA ориентируйся на URL + fingerprint + новое UI.
    11. Не выдумывай содержимое.
    12. Никогда не утверждай действие выполненным,
        если browser tool его не подтвердил.
    13. В конце дай краткий итог.
    """

    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Краткий итоговый результат")

# ============================================================
# DSPY TOOLS
# ============================================================

def create_browser_tools():

    def run_async_from_dspy(coro):
        if main_event_loop is None:
            raise RuntimeError("Основной asyncio loop не установлен")

        if main_event_loop.is_closed():
            raise RuntimeError("Основной asyncio loop закрыт")

        future = asyncio.run_coroutine_threadsafe(coro, main_event_loop)

        try:
            return future.result(timeout=90)
        except Exception as e:
            future.cancel()
            raise RuntimeError(f"Browser tool error: {e}") from e

    def tool_goto(url: str):
        return run_async_from_dspy(browser_goto(url))

    def tool_back():
        return run_async_from_dspy(browser_back())

    def tool_forward():
        return run_async_from_dspy(browser_forward())

    def tool_reload():
        return run_async_from_dspy(browser_reload())

    def tool_page_info():
        return run_async_from_dspy(browser_page_info())

    def tool_inspect_page(
        mode: str = "map",
        max_interactive: int = 120,
        max_links: int = 80,
        max_text: int = 12000,
    ):
        return run_async_from_dspy(
            browser_inspect(
                max_interactive=max_interactive,
                max_links=max_links,
                max_text=max_text,
                mode=mode if mode in ("map", "full") else "map",
            )
        )

    def tool_get_text(selector: str = "body"):
        return run_async_from_dspy(browser_get_text(selector))

    def tool_get_html(selector: str = "body"):
        return run_async_from_dspy(browser_get_html(selector))

    def tool_get_links():
        return run_async_from_dspy(browser_get_links())

    def tool_click(selector: str):
        return run_async_from_dspy(browser_click(selector))

    def tool_click_text(text: str):
        return run_async_from_dspy(browser_click_text(text))

    def tool_click_role(role: str, name: str = ""):
        return run_async_from_dspy(browser_click_role(role, name))

    def tool_fill(selector: str, text: str):
        return run_async_from_dspy(browser_fill(selector, text))

    def tool_fill_label(label: str, text: str):
        return run_async_from_dspy(browser_fill_label(label, text))

    def tool_fill_placeholder(placeholder: str, text: str):
        return run_async_from_dspy(browser_fill_placeholder(placeholder, text))

    def tool_type(selector: str, text: str):
        return run_async_from_dspy(browser_type(selector, text))

    def tool_press(selector: str, key: str):
        return run_async_from_dspy(browser_press(selector, key))

    def tool_key(key: str):
        return run_async_from_dspy(browser_key(key))

    def tool_wait(milliseconds: int = 1000):
        return run_async_from_dspy(browser_wait(milliseconds))

    def tool_wait_selector(selector: str, timeout: int = 10000):
        return run_async_from_dspy(browser_wait_selector(selector, timeout))

    def tool_select(selector: str, value: str):
        return run_async_from_dspy(browser_select(selector, value))

    def tool_check(selector: str):
        return run_async_from_dspy(browser_check(selector))

    def tool_uncheck(selector: str):
        return run_async_from_dspy(browser_uncheck(selector))

    def tool_hover(selector: str):
        return run_async_from_dspy(browser_hover(selector))

    def tool_attribute(selector: str, attribute: str):
        return run_async_from_dspy(browser_attribute(selector, attribute))

    def tool_count(selector: str):
        return run_async_from_dspy(browser_count(selector))

    def tool_javascript(expression: str):
        return run_async_from_dspy(browser_js(expression))

    def tool_screenshot():
        return run_async_from_dspy(browser_screenshot())

    def tool_content():
        return run_async_from_dspy(browser_content())

    return [
        Tool(tool_goto),
        Tool(tool_back),
        Tool(tool_forward),
        Tool(tool_reload),
        Tool(tool_page_info),
        Tool(tool_inspect_page),
        Tool(tool_get_text),
        Tool(tool_get_html),
        Tool(tool_get_links),
        Tool(tool_click),
        Tool(tool_click_text),
        Tool(tool_click_role),
        Tool(tool_fill),
        Tool(tool_fill_label),
        Tool(tool_fill_placeholder),
        Tool(tool_type),
        Tool(tool_press),
        Tool(tool_key),
        Tool(tool_wait),
        Tool(tool_wait_selector),
        Tool(tool_select),
        Tool(tool_check),
        Tool(tool_uncheck),
        Tool(tool_hover),
        Tool(tool_attribute),
        Tool(tool_count),
        Tool(tool_javascript),
        Tool(tool_screenshot),
        Tool(tool_content),
    ]

# ============================================================
# DSPY AGENT
# ============================================================

def init_dspy():
    global dspy_agent_instance

    if not os.environ.get("AGNES_API_KEY"):
        logger.warning("AGNES_API_KEY не задан")
        return False

    try:
        lm = AgnesLM(
            api_key=os.environ.get("AGNES_API_KEY"),
            temperature=0.2,
            max_tokens=4000,
        )

        dspy_lib.configure(lm=lm)  # ← dspy_lib.configure
        tools = create_browser_tools()

        if REACT_V2_AVAILABLE:
            try:
                dspy_agent_instance = ReActV2(
                    BrowserTask,
                    tools=tools,
                    max_iters=15,
                )
                logger.info("Используется ReActV2")
            except Exception as e:
                logger.warning("ReActV2 error: %s", e)
                dspy_agent_instance = dspy_lib.ReAct(  # ← dspy_lib.ReAct
                    BrowserTask,
                    tools=tools,
                    max_iters=15,
                )
        else:
            dspy_agent_instance = dspy_lib.ReAct(  # ← dspy_lib.ReAct
                BrowserTask,
                tools=tools,
                max_iters=15,
            )

        logger.info("DSPy создан. Tools: %s", len(tools))
        return True

    except Exception:
        logger.exception("DSPy init error")
        dspy_agent_instance = None
        return False


def run_agent(question: str):
    if not dspy_agent_instance:
        return "DSPy агент не инициализирован"

    with agent_lock:
        try:
            result = dspy_agent_instance(question=question)

            answer = getattr(result, "answer", None)

            if answer is None and isinstance(result, dict):
                answer = result.get("answer")

            if answer is None:
                answer = str(result)

            answer = str(answer).strip()
            return answer or "Пустой ответ DSPy"

        except Exception as e:
            logger.exception("DSPy error")
            return f"Ошибка агента: {type(e).__name__}: {e}"


def set_main_event_loop(loop):
    global main_event_loop
    main_event_loop = loop