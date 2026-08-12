# bot.py - полный рабочий бот с DSPy промтом 
import os
import sys
import asyncio
import logging
import time
import base64

# ============================================================
# 1. НАСТРОЙКА ЛОГГЕРА
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# 2. ПАПКИ
# ============================================================

SCREENSHOTS_DIR = '/app/screenshots'
LOGS_DIR = '/app/logs'
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# ============================================================
# 3. BROWSER HARNESS
# ============================================================

sys.path.insert(0, "browser-harness/src")

from browser_harness.helpers import (
    new_tab,
    goto_url,
    wait_for_load,
    close_tab,
    capture_screenshot,
    page_info,
    js,
    fill_input,
    click_at_xy,
    scroll,
    list_tabs,
    switch_tab,
    type_text,
    press_key,
)
from browser_harness.admin import ensure_daemon

# ============================================================
# 4. КУКИ
# ============================================================

try:
    from cookies import COOKIES
    logger.info(f"🍪 Загружено {len(COOKIES)} кук")
except ImportError:
    COOKIES = []
    logger.warning("⚠️ cookies.py не найден")

# ============================================================
# 5. TELEGRAM
# ============================================================

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.helpers import escape_markdown

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# ============================================================
# 6. CDP URL
# ============================================================

CDP_URL = os.environ.get("CDP_URL", "https://9d683906-74b6-44a1-a138-c33b957fb907.cdp.browser-use.com")

# ============================================================
# 7. DSPy С ПОЛНЫМ ПРОМТОМ
# ============================================================

DSPY_ENABLED = os.environ.get("AGNES_API_KEY") is not None

if DSPY_ENABLED:
    import dspy
    from dspy import Signature, InputField, OutputField, settings, ReActV2, Tool
    
    # ============================================================
    # ПОЛНАЯ СИГНАТУРА С ПРОМТОМ
    # ============================================================
    
    class BrowserTask(Signature):
        """
        Ты агент с доступом к браузеру через Browser Harness.
        
        ДОСТУПНЫЕ ИНСТРУМЕНТЫ BROWSER HARNESS:
        
        1. Навигация:
           - tool_goto_url(url) - перейти на сайт
           - tool_wait_for_load() - дождаться загрузки
           - tool_new_tab() - открыть новую вкладку
           - tool_close_tab() - закрыть вкладку
           - tool_switch_tab(tab_id) - переключить вкладку
           - tool_list_tabs() - список всех вкладок
        
        2. Информация о странице:
           - tool_page_info() - URL и заголовок
           - tool_get_text() - весь текст на странице
           - tool_get_links() - все ссылки
           - tool_get_buttons() - все кнопки
           - tool_get_headings() - все заголовки (h1-h6)
        
        3. Взаимодействие со страницей:
           - tool_js(expression) - выполнить JavaScript
           - tool_fill_input(selector, text) - заполнить поле ввода
           - tool_click_at_xy(x, y) - кликнуть по координатам
           - tool_type_text(text) - ввести текст
           - tool_press_key(key) - нажать клавишу
           - tool_scroll(x, y) - прокрутить страницу
        
        4. Скриншоты:
           - tool_capture_screenshot(filename) - сделать скриншот
        
        ПРАВИЛА:
        - Всегда используй инструменты Browser Harness
        - Для получения текста со страницы используй tool_get_text
        - Для кликов используй tool_click_at_xy
        - Для заполнения форм используй tool_fill_input
        - Если нужно выполнить сложные действия - используй tool_js
        - Всегда проверяй результат выполнения действия
        - Если инструмент вернул ошибку - попробуй другой подход
        """
        
        question = InputField(desc="Задача пользователя на русском языке")
        answer = OutputField(desc="Подробный ответ с результатами выполнения задачи")
    
    # ============================================================
    # АДАПТЕР ДЛЯ AGNES AI
    # ============================================================
    
    class AgnesLM(dspy.LM):
        def __init__(self):
            super().__init__(model="agnes")
            self.api_key = os.environ.get("AGNES_API_KEY")
            self.model = "agnes-2.0-flash"
            self.provider = "agnes-ai"
        
        def forward(self, prompt=None, messages=None, **kwargs):
            import httpx
            try:
                with httpx.Client(timeout=120) as client:
                    resp = client.post(
                        "https://apihub.agnes-ai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={
                            "model": self.model,
                            "messages": messages or [{"role": "user", "content": prompt}],
                            "temperature": kwargs.get("temperature", 0.3),
                            "max_tokens": kwargs.get("max_tokens", 3000)
                        }
                    )
                    data = resp.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        return [data["choices"][0]["message"]["content"]]
                    return ["Ошибка: пустой ответ от API"]
            except Exception as e:
                return [f"Ошибка: {str(e)}"]
        
        def __call__(self, prompt=None, messages=None, **kwargs):
            return self.forward(prompt=prompt, messages=messages, **kwargs)
    
    # ============================================================
    # ВСЕ ИНСТРУМЕНТЫ BROWSER HARNESS ДЛЯ DSPy
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
            return str(result) if result is not None else "✅ JavaScript выполнен"
        except Exception as e:
            return f"❌ Ошибка JavaScript: {e}"
    
    def tool_capture_screenshot(filename: str = None) -> str:
        """Сделать скриншот страницы"""
        try:
            if not filename:
                filename = f"screenshot_{int(time.time())}.png"
            full_path = os.path.join(SCREENSHOTS_DIR, filename)
            capture_screenshot(path=full_path)
            return f"✅ Скриншот сохранен: {filename}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    def tool_page_info() -> str:
        """Получить информацию о странице (URL, Title)"""
        try:
            info = page_info()
            return f"URL: {info.get('url', 'unknown')}\nTitle: {info.get('title', 'unknown')}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    def tool_get_text() -> str:
        """Получить весь текст на странице"""
        try:
            result = js('document.body.innerText')
            text = str(result)
            if text and len(text) > 10:
                return text[:5000]
            return "❌ Текст не найден или страница пуста"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    def tool_get_links() -> str:
        """Получить все ссылки на странице"""
        try:
            result = js('Array.from(document.querySelectorAll("a")).map(el => el.href).filter(h => h)')
            if isinstance(result, list) and result:
                links = [str(item) for item in result if item]
                return f"Ссылки ({len(links)}): {links[:20]}" + ("..." if len(links) > 20 else "")
            return "❌ Ссылок не найдено"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    def tool_get_buttons() -> str:
        """Получить все кнопки на странице"""
        try:
            result = js('Array.from(document.querySelectorAll("button, input[type=submit]")).map(el => el.innerText || el.value || el.type).filter(t => t.trim())')
            if isinstance(result, list) and result:
                buttons = [str(item).strip() for item in result if item and str(item).strip()]
                return f"Кнопки: {buttons[:20]}" + ("..." if len(buttons) > 20 else "")
            return "❌ Кнопок не найдено"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    def tool_get_headings() -> str:
        """Получить все заголовки на странице (h1-h6)"""
        try:
            result = js('Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6")).map(el => `${el.tagName}: ${el.innerText}`).filter(t => t.trim())')
            if isinstance(result, list) and result:
                headings = [str(item).strip() for item in result if item and str(item).strip()]
                return f"Заголовки:\n" + "\n".join(headings)
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
    
    # ============================================================
    # СОЗДАНИЕ АГЕНТА
    # ============================================================
    
    def init_dspy():
        lm = AgnesLM()
        settings.configure(lm=lm)
        
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
            Tool(tool_switch_tab),
            Tool(tool_close_tab),
            Tool(tool_fill_input),
            Tool(tool_click_at_xy),
            Tool(tool_type_text),
            Tool(tool_press_key),
            Tool(tool_scroll),
        ]
        
        try:
            agent = ReActV2(
                signature=BrowserTask,
                tools=tools,
                max_iters=10,
            )
            logger.info(f"✅ ReActV2 агент создан с {len(tools)} инструментами")
            return agent
        except Exception as e:
            logger.error(f"❌ Ошибка создания ReActV2: {e}")
            return None
    
    dspy_agent = init_dspy()
    logger.info("🧠 DSPy инициализирован")
else:
    dspy_agent = None
    logger.info("ℹ️ DSPy отключён (AGNES_API_KEY не задан)")

# ============================================================
# 8. ОСНОВНОЙ КЛАСС
# ============================================================

class HarnessBot:
    def __init__(self):
        self.tab = None
        self.is_ready = False
    
    async def start(self):
        """Запуск"""
        logger.info("🚀 Запуск Browser Harness...")
        
        os.environ["BU_CDP_URL"] = CDP_URL
        logger.info(f"🔗 BU_CDP_URL: {CDP_URL}")
        
        ensure_daemon()
        logger.info("✅ Демон подключен к браузеру")
        
        logger.info("🌐 Создаю вкладку...")
        self.tab = new_tab("https://example.com")
        wait_for_load()
        logger.info(f"✅ Вкладка создана: {self.tab}")
        
        if COOKIES:
            for cookie in COOKIES:
                try:
                    js(f"document.cookie = '{cookie['name']}={cookie['value']}; domain={cookie.get('domain', '')}; path=/'")
                except:
                    pass
            logger.info(f"🍪 Установлено {len(COOKIES)} кук")
        
        self.is_ready = True
        logger.info("✅ HarnessBot готов!")
        return self
    
    async def ask_dspy(self, question):
        """Задать вопрос DSPy агенту"""
        if not dspy_agent:
            return "❌ DSPy отключён. Установите AGNES_API_KEY"
        
        logger.info(f"🧠 DSPy запрос: {question}")
        try:
            result = dspy_agent(question=question)
            answer = getattr(result, 'answer', str(result))
            return answer if answer and answer.strip() else "❌ Агент вернул пустой ответ"
        except Exception as e:
            logger.error(f"❌ DSPy ошибка: {e}")
            return f"❌ Ошибка: {str(e)}"
    
    async def close(self):
        """Закрыть"""
        if self.tab:
            try:
                close_tab(self.tab)
            except:
                pass
        self.is_ready = False


# ============================================================
# 9. TELEGRAM КОМАНДЫ
# ============================================================

bot = None

async def start_command(update, context):
    await update.message.reply_text(
        "🤖 **Browser Bot**\n\n"
        "Команды:\n"
        "`/go <url>` - перейти на сайт\n"
        "`/screenshot` - сделать скриншот\n"
        "`/text` - получить текст страницы\n"
        "`/info` - информация о странице\n"
        "`/dspy <задача>` - задать вопрос AI-агенту\n\n"
        "Примеры /dspy:\n"
        "• открыть google.com и сделать скриншот\n"
        "• найти все ссылки на странице\n"
        "• заполнить форму логина",
        parse_mode='Markdown'
    )

async def go_command(update, context):
    if not context.args:
        await update.message.reply_text("Используй: /go https://example.com")
        return
    
    url = context.args[0]
    msg = await update.message.reply_text(f"🌐 Перехожу на {url}...")
    
    try:
        goto_url(url)
        wait_for_load()
        info = page_info()
        await msg.edit_text(
            f"✅ **Загружено**\n"
            f"URL: {info.get('url')}\n"
            f"Title: {info.get('title')}"
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")

async def screenshot_command(update, context):
    msg = await update.message.reply_text("📸 Делаю скриншот...")
    
    try:
        filename = f"screenshot_{int(time.time())}.png"
        path = os.path.join(SCREENSHOTS_DIR, filename)
        capture_screenshot(path=path)
        with open(path, 'rb') as f:
            await update.message.reply_photo(f)
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")

async def text_command(update, context):
    msg = await update.message.reply_text("📖 Получаю текст...")
    
    try:
        text = js('document.body.innerText')
        text = str(text)
        if len(text) > 4000:
            text = text[:4000] + "..."
        await msg.edit_text(f"📝 **Текст:**\n\n{escape_markdown(text, version=2)}", parse_mode='MarkdownV2')
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")

async def info_command(update, context):
    try:
        info = page_info()
        await update.message.reply_text(
            f"📄 **Информация**\n"
            f"URL: {info.get('url')}\n"
            f"Title: {info.get('title')}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def dspy_command(update, context):
    if not dspy_agent:
        await update.message.reply_text(
            "❌ DSPy отключён.\n"
            "Установите переменную окружения AGNES_API_KEY"
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "🧠 **DSPy Agent**\n\n"
            "Опиши задачу на русском языке:\n"
            "`/dspy открыть google.com и сделать скриншот`\n\n"
            "Что умеет:\n"
            "• Переход по URL\n"
            "• Скриншоты\n"
            "• Получение текста и ссылок\n"
            "• Клики и заполнение форм\n"
            "• Работа с вкладками\n"
            "• Выполнение JavaScript",
            parse_mode='Markdown'
        )
        return
    
    question = " ".join(context.args)
    msg = await update.message.reply_text("🧠 Думаю...")
    
    try:
        answer = await bot.ask_dspy(question)
        if len(answer) > 4000:
            answer = answer[:4000] + "\n\n... (обрезано)"
        await msg.edit_text(
            f"✅ **Результат:**\n\n{escape_markdown(answer, version=2)}",
            parse_mode='MarkdownV2'
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")


# ============================================================
# 10. ЗАПУСК
# ============================================================

async def main():
    global bot
    
    bot = HarnessBot()
    await bot.start()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("go", go_command))
    app.add_handler(CommandHandler("screenshot", screenshot_command))
    app.add_handler(CommandHandler("text", text_command))
    app.add_handler(CommandHandler("info", info_command))
    if dspy_agent:
        app.add_handler(CommandHandler("dspy", dspy_command))
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    logger.info("🚀 Бот запущен!")
    logger.info(f"🔗 CDP: {CDP_URL}")
    logger.info(f"🧠 DSPy: {'✅' if dspy_agent else '❌'}")
    logger.info(f"🍪 Куки: {'✅' if COOKIES else '❌'}")
    
    try:
        while True:
            await asyncio.sleep(60)
            logger.info("💓 Bot alive")
    except KeyboardInterrupt:
        await bot.close()
        logger.info("👋 Бот остановлен")

if __name__ == "__main__":
    asyncio.run(main())