# bot.py - полностью автоматический бот с Browser Use Cloud API
import os
import sys
import asyncio
import logging
import time
from datetime import datetime, timedelta

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
# 3. SDK BROWSER USE
# ============================================================

from browser_use_sdk.v3 import AsyncBrowserUse

# ============================================================
# 4. BROWSER HARNESS
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
)
from browser_harness.admin import ensure_daemon

# ============================================================
# 5. КУКИ
# ============================================================

try:
    from cookies import COOKIES
    logger.info(f"🍪 Загружено {len(COOKIES)} кук")
except ImportError:
    COOKIES = []
    logger.warning("⚠️ cookies.py не найден")

# ============================================================
# 6. TELEGRAM
# ============================================================

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.helpers import escape_markdown

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# ============================================================
# 7. DSPy
# ============================================================

DSPY_ENABLED = os.environ.get("AGNES_API_KEY") is not None

if DSPY_ENABLED:
    import dspy
    from dspy import Signature, InputField, OutputField, settings, ReActV2, Tool
    
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
        """
        
        question = InputField(desc="Задача пользователя на русском языке")
        answer = OutputField(desc="Подробный ответ с результатами выполнения задачи")
    
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
    
    def init_dspy():
        lm = AgnesLM()
        settings.configure(lm=lm)
        
        # Инструменты
        def tool_new_tab() -> str:
            try:
                new_tab()
                return "✅ Новая вкладка открыта"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_goto_url(url: str) -> str:
            try:
                goto_url(url)
                wait_for_load()
                return f"✅ Перешел на {url}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_wait_for_load() -> str:
            try:
                wait_for_load()
                return "✅ Страница загружена"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_js(expression: str) -> str:
            try:
                result = js(expression)
                return str(result) if result is not None else "✅ JavaScript выполнен"
            except Exception as e:
                return f"❌ Ошибка JavaScript: {e}"
        
        def tool_capture_screenshot(filename: str = None) -> str:
            try:
                if not filename:
                    filename = f"screenshot_{int(time.time())}.png"
                full_path = os.path.join(SCREENSHOTS_DIR, filename)
                capture_screenshot(path=full_path)
                return f"✅ Скриншот сохранен: {filename}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_page_info() -> str:
            try:
                info = page_info()
                return f"URL: {info.get('url', 'unknown')}\nTitle: {info.get('title', 'unknown')}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_get_text() -> str:
            try:
                result = js('document.body.innerText')
                text = str(result)
                if text and len(text) > 10:
                    return text[:5000]
                return "❌ Текст не найден или страница пуста"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_get_links() -> str:
            try:
                result = js('Array.from(document.querySelectorAll("a")).map(el => el.href).filter(h => h)')
                if isinstance(result, list) and result:
                    links = [str(item) for item in result if item]
                    return f"Ссылки ({len(links)}): {links[:20]}" + ("..." if len(links) > 20 else "")
                return "❌ Ссылок не найдено"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_get_buttons() -> str:
            try:
                result = js('Array.from(document.querySelectorAll("button, input[type=submit]")).map(el => el.innerText || el.value || el.type).filter(t => t.trim())')
                if isinstance(result, list) and result:
                    buttons = [str(item).strip() for item in result if item and str(item).strip()]
                    return f"Кнопки: {buttons[:20]}" + ("..." if len(buttons) > 20 else "")
                return "❌ Кнопок не найдено"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_get_headings() -> str:
            try:
                result = js('Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6")).map(el => `${el.tagName}: ${el.innerText}`).filter(t => t.trim())')
                if isinstance(result, list) and result:
                    headings = [str(item).strip() for item in result if item and str(item).strip()]
                    return f"Заголовки:\n" + "\n".join(headings)
                return "❌ Заголовков не найдено"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_list_tabs() -> str:
            try:
                tabs = list_tabs()
                return f"Вкладки: {tabs}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_switch_tab(tab_id: int) -> str:
            try:
                switch_tab(tab_id)
                return f"✅ Переключился на вкладку {tab_id}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_close_tab() -> str:
            try:
                close_tab()
                return "✅ Вкладка закрыта"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_fill_input(selector: str, text: str) -> str:
            try:
                fill_input(selector, text)
                return f"✅ Заполнено: {selector} -> {text}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_click_at_xy(x: int, y: int) -> str:
            try:
                click_at_xy(x, y)
                return f"✅ Клик по ({x}, {y})"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_scroll(dx: int, dy: int) -> str:
            try:
                scroll(dx, dy)
                return f"✅ Прокрутка на ({dx}, {dy})"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
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
            Tool(tool_scroll),
        ]
        
        try:
            agent = ReActV2(
                signature=BrowserTask,
                tools=tools,
                max_iters=15,
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
# 8. УПРАВЛЕНИЕ СЕССИЯМИ BROWSER USE
# ============================================================

class BrowserSessionManager:
    """Автоматическое управление сессиями Browser Use Cloud"""
    
    def __init__(self):
        self.client = None
        self.current_cdp_url = None
        self.session_created_at = None
        self.session_lifetime = 14  # минут (пересоздаём за 1 минуту до истечения)
        self.is_running = False
        self.renew_task = None
    
    async def start(self):
        """Запустить менеджер"""
        self.client = AsyncBrowserUse()
        self.is_running = True
        
        # Создаём первую сессию
        await self._create_session()
        
        # Запускаем фоновое обновление
        self.renew_task = asyncio.create_task(self._auto_renew())
        
        logger.info("✅ BrowserSessionManager запущен")
        return self
    
    async def _create_session(self):
        """Создать новую сессию"""
        logger.info("🚀 Создаю новую сессию в Browser Use Cloud...")
        
        try:
            # Создаём браузер через SDK
            result = await self.client.create_browser(
                timeout=15,  # минут
                headless=True
            )
            
            # Получаем CDP URL
            self.current_cdp_url = result.cdp_url
            self.session_created_at = datetime.now()
            
            logger.info(f"✅ Сессия создана: {self.current_cdp_url}")
            logger.info(f"⏱️ Сессия активна до: {self.session_created_at + timedelta(minutes=15)}")
            
            return self.current_cdp_url
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания сессии: {e}")
            # Пробуем через HTTP напрямую
            return await self._create_session_http()
    
    async def _create_session_http(self):
        """Создать сессию через HTTP API (если SDK не работает)"""
        import httpx
        
        api_key = os.environ.get("BROWSER_USE_API_KEY")
        if not api_key:
            raise ValueError("BROWSER_USE_API_KEY не задан!")
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.browser-use.com/api/v3/browsers",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"timeout": 15}
            )
            resp.raise_for_status()
            data = resp.json()
            
            self.current_cdp_url = data["cdp_url"]
            self.session_created_at = datetime.now()
            
            logger.info(f"✅ Сессия создана (HTTP): {self.current_cdp_url}")
            return self.current_cdp_url
    
    async def _auto_renew(self):
        """Фоновое обновление сессии"""
        while self.is_running:
            # Проверяем, не пора ли обновить
            if self.session_created_at:
                elapsed = (datetime.now() - self.session_created_at).total_seconds() / 60
                
                if elapsed >= self.session_lifetime:
                    logger.info(f"⏰ Сессии {elapsed:.1f} минут - обновляю...")
                    await self.renew_session()
            
            # Проверяем каждые 30 секунд
            await asyncio.sleep(30)
    
    async def renew_session(self):
        """Принудительное обновление сессии"""
        logger.info("🔄 Пересоздаю сессию...")
        
        # Закрываем старую сессию
        try:
            await self.client.close_browser()
        except:
            pass
        
        # Создаём новую
        await self._create_session()
        
        # Обновляем переменную окружения для Browser Harness
        os.environ["BU_CDP_URL"] = self.current_cdp_url
        
        logger.info("✅ Сессия обновлена")
        return self.current_cdp_url
    
    async def get_cdp_url(self):
        """Получить текущий CDP URL"""
        if not self.current_cdp_url:
            await self._create_session()
        return self.current_cdp_url
    
    async def stop(self):
        """Остановить менеджер"""
        self.is_running = False
        
        if self.renew_task:
            self.renew_task.cancel()
        
        try:
            await self.client.close_browser()
            logger.info("✅ Сессия закрыта")
        except:
            pass


# ============================================================
# 9. ОСНОВНОЙ КЛАСС БОТА
# ============================================================

class HarnessBot:
    def __init__(self):
        self.tab = None
        self.is_ready = False
        self.session_manager = None
        self.cdp_url = None
    
    async def start(self):
        """Запуск с автоматическим управлением сессиями"""
        logger.info("🚀 Запуск Browser Harness с Auto-Renew...")
        
        # 1. Создаём менеджер сессий
        self.session_manager = BrowserSessionManager()
        await self.session_manager.start()
        
        # 2. Получаем CDP URL
        self.cdp_url = await self.session_manager.get_cdp_url()
        
        # 3. Настраиваем Browser Harness
        os.environ["BU_CDP_URL"] = self.cdp_url
        ensure_daemon()
        logger.info("✅ Демон подключен к браузеру")
        
        # 4. Создаём вкладку
        logger.info("🌐 Создаю вкладку...")
        self.tab = new_tab("https://example.com")
        wait_for_load()
        logger.info(f"✅ Вкладка создана: {self.tab}")
        
        # 5. Устанавливаем куки
        if COOKIES:
            for cookie in COOKIES:
                try:
                    js(f"document.cookie = '{cookie['name']}={cookie['value']}; domain={cookie.get('domain', '')}; path=/'")
                except:
                    pass
            logger.info(f"🍪 Установлено {len(COOKIES)} кук")
        
        self.is_ready = True
        logger.info("✅ HarnessBot готов!")
        logger.info(f"⏱️ Сессия будет автоматически обновляться каждые 14 минут")
        return self
    
    async def ensure_session(self):
        """Проверить и обновить сессию если нужно"""
        if self.session_manager:
            # Если сессия обновилась - переподключаем Browser Harness
            new_url = await self.session_manager.get_cdp_url()
            if new_url != self.cdp_url:
                logger.info("🔄 Сессия обновилась, переподключаю...")
                self.cdp_url = new_url
                os.environ["BU_CDP_URL"] = self.cdp_url
                # Пересоздаём вкладку
                if self.tab:
                    try:
                        close_tab(self.tab)
                    except:
                        pass
                self.tab = new_tab("https://example.com")
                wait_for_load()
                logger.info("✅ Переподключено")
    
    async def ask_dspy(self, question):
        """Задать вопрос DSPy агенту"""
        if not dspy_agent:
            return "❌ DSPy отключён. Установите AGNES_API_KEY"
        
        # Проверяем сессию перед выполнением
        await self.ensure_session()
        
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
        
        if self.session_manager:
            await self.session_manager.stop()
        
        self.is_ready = False
        logger.info("✅ Закрыто")


# ============================================================
# 10. TELEGRAM КОМАНДЫ
# ============================================================

bot = None

async def start_command(update, context):
    await update.message.reply_text(
        "🤖 **Browser Bot (Auto-Renew)**\n\n"
        "Команды:\n"
        "`/go <url>` - перейти на сайт\n"
        "`/screenshot` - сделать скриншот\n"
        "`/text` - получить текст страницы\n"
        "`/info` - информация о странице\n"
        "`/dspy <задача>` - задать вопрос AI-агенту\n\n"
        "⚡ Сессия автоматически обновляется каждые 14 минут",
        parse_mode='Markdown'
    )

async def go_command(update, context):
    if not context.args:
        await update.message.reply_text("Используй: /go https://example.com")
        return
    
    url = context.args[0]
    msg = await update.message.reply_text(f"🌐 Перехожу на {url}...")
    
    try:
        await bot.ensure_session()
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
        await bot.ensure_session()
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
        await bot.ensure_session()
        text = js('document.body.innerText')
        text = str(text)
        if len(text) > 4000:
            text = text[:4000] + "..."
        await msg.edit_text(f"📝 **Текст:**\n\n{escape_markdown(text, version=2)}", parse_mode='MarkdownV2')
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")

async def info_command(update, context):
    try:
        await bot.ensure_session()
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
# 11. ЗАПУСК
# ============================================================

async def main():
    global bot
    
    # Проверяем API ключи
    if not os.environ.get("BROWSER_USE_API_KEY"):
        logger.error("❌ BROWSER_USE_API_KEY не задан!")
        return
    
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
    logger.info(f"🔗 CDP: {bot.cdp_url}")
    logger.info(f"🧠 DSPy: {'✅' if dspy_agent else '❌'}")
    logger.info(f"🍪 Куки: {'✅' if COOKIES else '❌'}")
    logger.info("⏱️ Сессия автоматически обновляется каждые 14 минут")
    
    try:
        while True:
            await asyncio.sleep(60)
            logger.info("💓 Bot alive")
    except KeyboardInterrupt:
        await bot.close()
        logger.info("👋 Бот остановлен")

if __name__ == "__main__":
    asyncio.run(main())