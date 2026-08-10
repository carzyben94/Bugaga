import os
import sys
import time
import logging
import asyncio
import httpx
import warnings
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.helpers import escape_markdown

import dspy
from dspy import Signature, InputField, OutputField, settings, ReActV2, Tool

warnings.filterwarnings("ignore")

# Логи
LOGS_DIR = '/app/logs'
SCREENSHOTS_DIR = '/app/screenshots'
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Пути
sys.path.insert(0, "browser-harness/src")
from browser_harness.helpers import (
    new_tab, goto_url, wait_for_load, page_info, capture_screenshot,
    click_at_xy, type_text, press_key, scroll, js,
    list_tabs, current_tab, close_tab, switch_tab, fill_input
)
from browser_harness.admin import ensure_daemon

# ============================================================
# DSPy АДАПТЕР
# ============================================================

class AgnesLM(dspy.LM):
    def __init__(self, model="agnes-2.0-flash", api_key=None, **kwargs):
        self.api_key = api_key or os.environ.get("AGNES_API_KEY")
        self.model = model
        super().__init__(model=model, model_type="chat", temperature=0.3, max_tokens=2000, cache=False)
        self.provider = "agnes-ai"
        self.forward_contract = "legacy"
    
    def forward(self, prompt=None, messages=None, **kwargs):
        if not self.api_key:
            return ["Ошибка: API ключ не задан"]
        
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": messages or [{"role": "user", "content": prompt or ""}],
            "temperature": 0.3,
            "max_tokens": 2000
        }
        
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post("https://apihub.agnes-ai.com/v1/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return [data["choices"][0]["message"]["content"]] if data.get("choices") else ["Ошибка: пустой ответ"]
        except Exception as e:
            return [f"Ошибка: {str(e)}"]

# ============================================================
# СИГНАТУРА И ИНСТРУМЕНТЫ
# ============================================================

class BrowserTask(Signature):
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Ответ на задачу")

def tool_new_tab():
    try: new_tab(); return "✅ Новая вкладка открыта"
    except Exception as e: return f"❌ Ошибка: {e}"

def tool_goto_url(url: str):
    try: goto_url(url); wait_for_load(); return f"✅ Перешел на {url}"
    except Exception as e: return f"❌ Ошибка: {e}"

def tool_capture_screenshot(filename: str = None):
    try:
        if not filename: filename = f"screenshot_{int(time.time())}.png"
        capture_screenshot(path=os.path.join(SCREENSHOTS_DIR, filename))
        return f"✅ Скриншот: {filename}"
    except Exception as e: return f"❌ Ошибка: {e}"

def tool_fill_input(selector: str, text: str):
    try: fill_input(selector, text); return f"✅ Заполнено: {selector}"
    except Exception as e: return f"❌ Ошибка: {e}"

def tool_click_at_xy(x: int, y: int):
    try: click_at_xy(x, y); return f"✅ Клик по ({x}, {y})"
    except Exception as e: return f"❌ Ошибка: {e}"

def tool_type_text(text: str):
    try: type_text(text); return f"✅ Введено: {text}"
    except Exception as e: return f"❌ Ошибка: {e}"

def tool_press_key(key: str):
    try: press_key(key); return f"✅ Нажата клавиша: {key}"
    except Exception as e: return f"❌ Ошибка: {e}"

def tool_scroll(dx: int, dy: int):
    try: scroll(dx, dy); return f"✅ Прокрутка на ({dx}, {dy})"
    except Exception as e: return f"❌ Ошибка: {e}"

def tool_js(expression: str):
    try:
        result = js(expression)
        return str(result.get('result', result)) if isinstance(result, dict) else str(result)
    except Exception as e: return f"❌ Ошибка: {e}"

def tool_page_info():
    try: info = page_info(); return f"URL: {info.get('url')}\nTitle: {info.get('title')}"
    except Exception as e: return f"❌ Ошибка: {e}"

def tool_list_tabs():
    try: return f"Вкладки: {list_tabs()}"
    except Exception as e: return f"❌ Ошибка: {e}"

def tool_switch_tab(tab_id: int):
    try: switch_tab(tab_id); return f"✅ Переключился на {tab_id}"
    except Exception as e: return f"❌ Ошибка: {e}"

def tool_close_tab():
    try: close_tab(); return "✅ Вкладка закрыта"
    except Exception as e: return f"❌ Ошибка: {e}"

# ============================================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================================

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

browser_agent = None
if AGNES_API_KEY:
    try:
        settings.configure(lm=AgnesLM(api_key=AGNES_API_KEY))
        browser_agent = ReActV2(
            signature=BrowserTask,
            tools=[
                Tool(tool_new_tab), Tool(tool_goto_url), Tool(tool_capture_screenshot),
                Tool(tool_fill_input), Tool(tool_click_at_xy), Tool(tool_type_text),
                Tool(tool_press_key), Tool(tool_scroll), Tool(tool_js),
                Tool(tool_page_info), Tool(tool_list_tabs), Tool(tool_switch_tab),
                Tool(tool_close_tab)
            ],
            max_iters=10
        )
        logger.info("✅ ReActV2 агент создан")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

# ============================================================
# ЗАПУСК БРАУЗЕРА
# ============================================================

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

os.environ["BU_CDP_URL"] = "http://localhost:9222"
ensure_daemon()
logger.info("✅ Браузер готов")

# ============================================================
# КОМАНДЫ
# ============================================================

async def start(update, context):
    await update.message.reply_text("🧠 **DSPy Браузерный агент**\n\n/dspy <запрос> — выполнить задачу\n/log — скачать логи")

async def log(update, context):
    try:
        with open(os.path.join(LOGS_DIR, 'bot.log'), 'rb') as f:
            await update.message.reply_document(f, filename='bot.log')
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)[:200]}")

async def dspy_command(update, context):
    if not browser_agent:
        await update.message.reply_text("❌ DSPy не инициализирован")
        return
    if not context.args:
        await update.message.reply_text("Пример: /dspy открыть google.com и сделать скриншот")
        return
    
    query = " ".join(context.args)
    msg = await update.message.reply_text("🧠 Думаю...")
    
    try:
        result = browser_agent(question=query)
        answer = getattr(result, 'answer', str(result))
        await msg.edit_text(f"✅ {escape_markdown(answer[:4000], version=2)}", parse_mode='MarkdownV2')
    except Exception as e:
        await msg.edit_text(f"❌ {str(e)[:200]}")

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("log", log))
    app.add_handler(CommandHandler("dspy", dspy_command))
    logger.info("🚀 Запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()