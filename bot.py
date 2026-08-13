import os
import sys
import asyncio
import logging
import subprocess
import json
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.helpers import escape_markdown
from cloakbrowser import launch_async

# ============================================================
# 1. НАСТРОЙКА ПУТЕЙ И ЛОГГЕРА
# ============================================================

# Добавляем путь к Browser Harness
sys.path.insert(0, "browser-harness/src")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# 2. ИМПОРТ BROWSER HARNESS
# ============================================================

try:
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
    HARNESS_AVAILABLE = True
    logger.info("✅ Browser Harness загружен")
except ImportError as e:
    logger.warning(f"⚠️ Browser Harness не найден: {e}")
    HARNESS_AVAILABLE = False

# ============================================================
# 3. ИМПОРТЫ DSPy
# ============================================================

import warnings
import httpx
import dspy
from dspy import Signature, InputField, OutputField, settings, ReActV2, Tool

warnings.filterwarnings("ignore")

# ============================================================
# 4. AGNES LM АДАПТЕР
# ============================================================

class AgnesLM(dspy.LM):
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
        api_messages = messages or [{"role": "user", "content": prompt or ""}]
        
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
                    return [data["choices"][0]["message"]["content"]]
                return ["Ошибка: пустой ответ"]
                
        except Exception as e:
            logger.error(f"❌ Agnes API: {e}")
            return [f"Ошибка: {str(e)}"]

# ============================================================
# 5. DSPy СИГНАТУРА ДЛЯ BROWSER HARNESS
# ============================================================

class BrowserTask(Signature):
    """
    Ты агент с доступом к браузеру через Browser Harness.
    
    ДОСТУПНЫЕ ИНСТРУМЕНТЫ:
    
    1. Навигация:
       - tool_goto_url(url) - перейти на сайт
       - tool_wait_for_load() - дождаться загрузки
       - tool_new_tab() - открыть новую вкладку
       - tool_close_tab() - закрыть вкладку
       - tool_switch_tab(tab_id) - переключить вкладку
       - tool_list_tabs() - список всех вкладок
    
    2. Информация:
       - tool_page_info() - URL и заголовок
       - tool_get_text() - весь текст на странице
       - tool_get_links() - все ссылки
       - tool_get_buttons() - все кнопки
       - tool_get_headings() - все заголовки
    
    3. Взаимодействие:
       - tool_js(expression) - выполнить JavaScript
       - tool_fill_input(selector, text) - заполнить поле
       - tool_click_at_xy(x, y) - кликнуть по координатам
       - tool_type_text(text) - ввести текст
       - tool_press_key(key) - нажать клавишу
       - tool_scroll(x, y) - прокрутить страницу
    
    4. Скриншоты:
       - tool_capture_screenshot(filename) - сделать скриншот
    
    ПРАВИЛА:
    - Всегда используй инструменты Browser Harness
    - Сначала открывай страницу через tool_goto_url
    - Для получения текста используй tool_get_text
    - Для кликов используй tool_click_at_xy
    - Отвечай на русском языке
    """
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Результат выполнения задачи")

# ============================================================
# 6. ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

browser_instance = None
page_instance = None
dspy_agent_instance = None
browser_harness_ready = False

# Папки для скриншотов
SCREENSHOTS_DIR = '/app/screenshots'
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# ============================================================
# 7. ИНИЦИАЛИЗАЦИЯ BROWSER HARNESS
# ============================================================

def init_browser_harness():
    """Инициализация Browser Harness"""
    global browser_harness_ready
    
    if not HARNESS_AVAILABLE:
        logger.warning("⚠️ Browser Harness недоступен")
        return False
    
    try:
        # Запускаем daemon
        ensure_daemon()
        logger.info("✅ Browser Harness daemon запущен")
        
        # Создаём вкладку
        new_tab("about:blank")
        wait_for_load()
        
        browser_harness_ready = True
        logger.info("✅ Browser Harness готов к работе")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Browser Harness: {e}")
        return False

# ============================================================
# 8. СОЗДАНИЕ ИНСТРУМЕНТОВ BROWSER HARNESS
# ============================================================

def create_harness_tools():
    """Создать инструменты Browser Harness для DSPy"""
    tools = []
    
    def tool_goto_url(url: str) -> str:
        """Перейти на URL и дождаться загрузки"""
        try:
            goto_url(url)
            wait_for_load()
            return f"✅ Перешел на {url}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_goto_url))
    
    def tool_wait_for_load() -> str:
        """Дождаться загрузки страницы"""
        try:
            wait_for_load()
            return "✅ Страница загружена"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_wait_for_load))
    
    def tool_new_tab() -> str:
        """Открыть новую вкладку"""
        try:
            new_tab()
            return "✅ Новая вкладка открыта"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_new_tab))
    
    def tool_close_tab() -> str:
        """Закрыть текущую вкладку"""
        try:
            close_tab()
            return "✅ Вкладка закрыта"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_close_tab))
    
    def tool_switch_tab(tab_id: int) -> str:
        """Переключиться на вкладку по ID"""
        try:
            switch_tab(tab_id)
            return f"✅ Переключился на вкладку {tab_id}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_switch_tab))
    
    def tool_list_tabs() -> str:
        """Список всех открытых вкладок"""
        try:
            tabs = list_tabs()
            return f"Вкладки: {tabs}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_list_tabs))
    
    def tool_page_info() -> str:
        """Получить информацию о странице"""
        try:
            info = page_info()
            return f"URL: {info.get('url', 'unknown')}\nTitle: {info.get('title', 'unknown')}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_page_info))
    
    def tool_get_text() -> str:
        """Получить весь текст на странице"""
        try:
            result = js('() => document.body.innerText')
            if isinstance(result, dict):
                text = result.get('result', str(result))
            else:
                text = str(result)
            if text and len(text) > 10:
                return text[:5000]
            return "❌ Текст не найден"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_get_text))
    
    def tool_get_links() -> str:
        """Получить все ссылки на странице"""
        try:
            result = js('() => Array.from(document.querySelectorAll("a")).map(el => el.href).filter(h => h)')
            if isinstance(result, list) and result:
                links = [str(item) for item in result if item]
                return f"Ссылки ({len(links)}): {links[:20]}" + ("..." if len(links) > 20 else "")
            return "❌ Ссылок не найдено"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_get_links))
    
    def tool_get_buttons() -> str:
        """Получить все кнопки на странице"""
        try:
            result = js('() => Array.from(document.querySelectorAll("button, input[type=submit]")).map(el => el.innerText || el.value || el.type).filter(t => t.trim())')
            if isinstance(result, list) and result:
                buttons = [str(item).strip() for item in result if item and str(item).strip()]
                return f"Кнопки: {buttons[:20]}" + ("..." if len(buttons) > 20 else "")
            return "❌ Кнопок не найдено"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_get_buttons))
    
    def tool_get_headings() -> str:
        """Получить все заголовки на странице"""
        try:
            result = js('() => Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6")).map(el => `${el.tagName}: ${el.innerText}`).filter(t => t.trim())')
            if isinstance(result, list) and result:
                headings = [str(item).strip() for item in result if item and str(item).strip()]
                return f"Заголовки:\n" + "\n".join(headings)
            return "❌ Заголовков не найдено"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_get_headings))
    
    def tool_js(expression: str) -> str:
        """Выполнить JavaScript на странице"""
        try:
            result = js(expression)
            if isinstance(result, dict):
                return str(result.get('result', result))
            return str(result) if result is not None else "✅ JavaScript выполнен"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_js))
    
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
    tools.append(Tool(tool_capture_screenshot))
    
    def tool_fill_input(selector: str, text: str) -> str:
        """Заполнить поле ввода по CSS селектору"""
        try:
            fill_input(selector, text)
            return f"✅ Заполнено: {selector} -> {text}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_fill_input))
    
    def tool_click_at_xy(x: int, y: int) -> str:
        """Кликнуть по координатам"""
        try:
            click_at_xy(x, y)
            return f"✅ Клик по ({x}, {y})"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_click_at_xy))
    
    def tool_type_text(text: str) -> str:
        """Ввести текст"""
        try:
            type_text(text)
            return f"✅ Введено: {text}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_type_text))
    
    def tool_press_key(key: str) -> str:
        """Нажать клавишу"""
        try:
            press_key(key)
            return f"✅ Нажата клавиша: {key}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_press_key))
    
    def tool_scroll(dx: int, dy: int) -> str:
        """Прокрутить страницу"""
        try:
            scroll(dx, dy)
            return f"✅ Прокрутка на ({dx}, {dy})"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_scroll))
    
    return tools

# ============================================================
# 9. ИНИЦИАЛИЗАЦИЯ DSPy
# ============================================================

def init_dspy():
    """Инициализировать DSPy с инструментами Browser Harness"""
    global dspy_agent_instance
    
    api_key = os.environ.get("AGNES_API_KEY")
    if not api_key:
        logger.warning("⚠️ AGNES_API_KEY не задан")
        return False
    
    try:
        # Создаём LM
        lm = AgnesLM(api_key=api_key, temperature=0.3, max_tokens=2000)
        settings.configure(lm=lm)
        logger.info("✅ DSPy настроен с AgnesLM")
        
        # Создаём инструменты
        tools = create_harness_tools()
        
        # Создаём агента
        dspy_agent_instance = ReActV2(
            signature=BrowserTask,
            tools=tools,
            max_iters=10,
        )
        
        logger.info(f"✅ DSPy агент создан с {len(tools)} инструментами")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации DSPy: {e}")
        return False

def run_agent(question: str) -> str:
    """Запустить DSPy агента"""
    if not dspy_agent_instance:
        return "❌ DSPy агент не инициализирован"
    
    try:
        result = dspy_agent_instance(question=question)
        answer = getattr(result, 'answer', str(result))
        return answer if answer and answer.strip() else "❌ Пустой ответ"
    except Exception as e:
        logger.error(f"❌ Ошибка выполнения: {e}")
        return f"❌ Ошибка: {str(e)}"

# ============================================================
# 10. ТЕЛЕГРАМ БОТ
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Команды:\n"
        "/check <url> - проверить сайт\n"
        "/dspy <запрос> - задать вопрос DSPy агенту\n"
        "/harness - статус Browser Harness\n"
        "/version - версия CloakBrowser"
    )

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /check https://example.com")
        return
    
    url = context.args[0]
    msg = await update.message.reply_text("⏳ Загружаю через CloakBrowser...")
    
    try:
        browser = await launch_async(
            headless=True,
            args=["--fingerprint"]
        )
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        title = await page.title()
        content = await page.content()
        await browser.close()
        
        response = f"✅ {title}\n\n{content[:500]}..."
        await msg.edit_text(response[:4096])
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def harness(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статус Browser Harness"""
    status = "✅ Browser Harness активен" if browser_harness_ready else "❌ Browser Harness не активен"
    harness_avail = "✅ Доступен" if HARNESS_AVAILABLE else "❌ Не установлен"
    
    await update.message.reply_text(
        f"📦 **Browser Harness**\n"
        f"• Статус: {harness_avail}\n"
        f"• Готовность: {status}\n"
        f"• DSPy: {'✅ Активен' if dspy_agent_instance else '❌ Отключен'}"
    )

async def version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = subprocess.run(
            ['cloakbrowser', 'info'],
            capture_output=True,
            text=True,
            timeout=5
        )
        info = result.stdout.strip() or result.stderr.strip()
        
        await update.message.reply_text(
            f"📦 **CloakBrowser**\n"
            f"• Статус: ✅ Работает\n"
            f"• Инфо: `{info[:200] if info else 'доступен'}`\n"
            f"• Harness: {'✅' if HARNESS_AVAILABLE else '❌'}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик /dspy с Browser Harness"""
    if not context.args:
        await update.message.reply_text(
            "🧠 **DSPy Agent с Browser Harness**\n\n"
            "Отправь задачу:\n"
            "`/dspy открой google.com и покажи заголовок`\n"
            "`/dspy сделай скриншот example.com`\n"
            "`/dspy найди все ссылки на python.org`\n"
            "`/dspy заполни форму поиска на google.com`\n\n"
            "Агент использует Browser Harness для управления браузером!",
            parse_mode='Markdown'
        )
        return
    
    if not dspy_agent_instance:
        await update.message.reply_text(
            "❌ **DSPy агент не инициализирован.**\n"
            "Проверьте переменную `AGNES_API_KEY`."
        )
        return
    
    if not browser_harness_ready:
        await update.message.reply_text(
            "❌ **Browser Harness не готов.**\n"
            "Проверьте установку browser-harness."
        )
        return
    
    user_query = " ".join(context.args)
    username = update.effective_user.username or "unknown"
    logger.info(f"👤 {username} DSPy: {user_query}")
    
    status_msg = await update.message.reply_text("🧠 Думаю и управляю браузером...")
    
    try:
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(
            None, run_agent, user_query
        )
        
        if not answer or answer.strip() == "":
            await status_msg.edit_text("❌ Агент вернул пустой ответ")
            return
        
        if len(answer) > 4000:
            answer = answer[:4000] + "\n\n... (обрезано)"
        
        answer_escaped = escape_markdown(answer, version=2)
        
        await status_msg.edit_text(
            f"✅ **Результат:**\n\n{answer_escaped}",
            parse_mode='MarkdownV2'
        )
        
    except Exception as e:
        logger.error(f"❌ DSPy ошибка: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# 11. ЗАПУСК
# ============================================================

def main():
    global browser_harness_ready
    
    logger.info("🚀 Инициализация...")
    
    # 1. Инициализируем Browser Harness
    if HARNESS_AVAILABLE:
        browser_harness_ready = init_browser_harness()
    
    # 2. Инициализируем DSPy
    dspy_ok = init_dspy()
    
    # 3. Создаём Telegram бота
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("harness", harness))
    app.add_handler(CommandHandler("version", version))
    app.add_handler(CommandHandler("dspy", dspy_command))
    
    logger.info("🚀 Бот запущен!")
    logger.info(f"🧠 DSPy статус: {'✅ Активен' if dspy_agent_instance else '❌ Отключен'}")
    logger.info(f"🔧 Harness статус: {'✅ Готов' if browser_harness_ready else '❌ Не готов'}")
    
    app.run_polling()

if __name__ == "__main__":
    main()