import os
import sys
import asyncio
import logging
import json
import io
import time
import random
import glob
from contextlib import redirect_stdout
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не установлен!")

# ============================================
# ИМПОРТЫ ZENDRIVER
# ============================================

try:
    import zendriver as zd
    ZENDRIVER_AVAILABLE = True
    logger.info("✅ Zendriver импортирован")
except ImportError:
    ZENDRIVER_AVAILABLE = False
    logger.error("❌ Zendriver не установлен!")

# ============================================
# КЛАСС ZENDRIVER MCP СЕРВЕР
# ============================================

class ZendriverMCP:
    """MCP-сервер для Zendriver"""
    
    def __init__(self):
        self.browser = None
        self.page = None
        self.is_ready = False
    
    async def start(self, headless: bool = True):
        """Запуск браузера Zendriver"""
        logger.info("🔄 Запускаю Zendriver...")
        self.browser = await zd.start(
            headless=headless,
            window_size=(1920, 1080),
            arguments=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--use-gl=angle",
                "--use-angle=gl-egl",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--remote-debugging-port=9222"
            ]
        )
        self.page = await self.browser.get("about:blank")
        self.is_ready = True
        logger.info("✅ Zendriver запущен")
        return self
    
    async def stop(self):
        """Остановка браузера"""
        if self.browser:
            await self.browser.stop()
            self.is_ready = False
            logger.info("✅ Zendriver остановлен")
    
    async def evaluate(self, script: str):
        """Выполнить JavaScript на странице"""
        if not self.is_ready or not self.page:
            return None
        try:
            return await self.page.evaluate(script)
        except Exception as e:
            logger.error(f"❌ Ошибка evaluate: {e}")
            return None
    
    async def navigate(self, url: str) -> str:
        if not self.is_ready:
            return "❌ Браузер не запущен"
        try:
            self.page = await self.browser.get(url)
            await asyncio.sleep(random.uniform(1, 3))
            return f"✅ Перешел на {url}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def screenshot(self, filename: str = None) -> str:
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            if not filename:
                timestamp = int(time.time())
                filename = f"screenshot_{timestamp}.png"
            await self.page.save_screenshot(filename)
            return f"✅ Скриншот сохранен: {filename}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def get_text(self) -> str:
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            content = await self.evaluate("document.body.innerText")
            return content[:5000] if content else "❌ Нет текста"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def get_html(self) -> str:
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            html = await self.evaluate("document.documentElement.outerHTML")
            return html[:5000] if html else "❌ Нет HTML"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def click(self, selector: str) -> str:
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            element = await self.page.find(selector).one()
            await element.click()
            return f"✅ Клик по {selector}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def type_text(self, selector: str, text: str) -> str:
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            element = await self.page.find(selector).one()
            await element.type_text(text)
            return f"✅ Введено: {text[:20]}..."
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def find_by_text(self, text: str) -> str:
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            element = await self.page.find(text).one()
            elem_text = await element.text()
            return f"✅ Найден элемент: {elem_text[:100]}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def get_title(self) -> str:
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            title = await self.evaluate("document.title")
            return f"✅ Заголовок: {title}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def get_url(self) -> str:
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            return f"✅ URL: {self.page.url}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def scroll(self, dx: int = 0, dy: int = 300) -> str:
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            await self.evaluate(f"window.scrollBy({dx}, {dy})")
            return f"✅ Прокрутка на ({dx}, {dy})"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def solve_turnstile(self) -> str:
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            if hasattr(self.page, 'solve_turnstile'):
                result = await self.page.solve_turnstile()
                return "✅ Turnstile решён" if result else "⚠️ Turnstile не найден"
            else:
                result = await self.evaluate("""
                    (function() {
                        if (typeof window.turnstile !== 'undefined') {
                            return 'found';
                        }
                        return 'not found';
                    })()
                """)
                return f"⚠️ Turnstile: {result}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def get_cookies(self) -> str:
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            cookies = await self.browser.cookies.get_all()
            cookies_list = []
            for cookie in cookies:
                cookies_list.append({
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                    "secure": cookie.secure,
                    "httpOnly": cookie.http_only
                })
            return f"✅ Куки: {json.dumps(cookies_list, indent=2)}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def set_cookies(self, cookies_json: str) -> str:
        if not self.is_ready:
            return "❌ Браузер не запущен"
        try:
            cookies = json.loads(cookies_json)
            for cookie in cookies:
                await self.browser.cookies.set(**cookie)
            return f"✅ Установлено {len(cookies)} кук"
        except Exception as e:
            return f"❌ Ошибка: {e}"

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
    logger.warning("⚠️ DSPy не установлен")

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
                    return [data["choices"][0]["message"]["content"]]
                return ["Ошибка: пустой ответ от API"]
        except Exception as e:
            logger.error(f"❌ Ошибка Agnes API: {e}")
            return [f"Ошибка: {str(e)}"]
    
    def __call__(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)

# ============================================
# СИГНАТУРА ДЛЯ АГЕНТА
# ============================================

class BrowserTask(Signature):
    """
    Ты агент с доступом к невидимому браузеру через Zendriver (CDP).
    Работай как опытный пользователь, который умеет обходить антибот-системы.
    
    ДОСТУПНЫЕ ИНСТРУМЕНТЫ (13 функций):
    
    1. Навигация:
       - navigate(url: str) -> str — перейти на URL и дождаться загрузки
       - get_url() -> str — получить текущий URL
       - get_title() -> str — получить заголовок страницы
    
    2. Получение данных:
       - get_text() -> str — получить весь текст страницы (первые 5000 символов)
       - get_html() -> str — получить HTML страницы (первые 5000 символов)
       - screenshot(filename: str = None) -> str — сделать скриншот
       - get_cookies() -> str — получить все куки в формате JSON
       - set_cookies(cookies_json: str) -> str — установить куки из JSON
    
    3. Взаимодействие с элементами (CSS-селекторы):
       - click(selector: str) -> str — кликнуть по элементу
       - type_text(selector: str, text: str) -> str — ввести текст в поле
       - find_by_text(text: str) -> str — найти элемент по тексту (автоповтор)
       - scroll(dx: int = 0, dy: int = 300) -> str — прокрутить страницу
    
    4. Обход защит:
       - solve_turnstile() -> str — обойти Cloudflare Turnstile (встроенный решатель)
    
    ПРАВИЛА РАБОТЫ:
    1. Сначала используй navigate(url) для перехода на сайт
    2. Всегда проверяй, что страница загрузилась (get_title или get_text)
    3. Для поиска элемента используй find_by_text(text), а затем click() или type_text()
    4. Для заполнения форм: find_by_text() → click() → type_text()
    5. Если видишь Cloudflare — вызови solve_turnstile()
    6. Делай скриншоты для проверки результата
    7. При работе с X.com используй куки и избегай частых запросов
    
    СТРАТЕГИЯ ПО УМОЛЧАНИЮ:
    1. navigate(url) — открыть страницу
    2. get_title() — проверить загрузку
    3. find_by_text(ключевое_слово) — найти элемент
    4. click() или type_text() — взаимодействовать
    5. screenshot() — проверить результат
    """
    
    question = InputField(desc="Задача пользователя на естественном языке")
    answer = OutputField(desc="Результат выполнения задачи с использованием Zendriver")

# ============================================
# СОЗДАНИЕ АГЕНТА
# ============================================

def create_tool(func, name: str, description: str):
    """Создать dspy.Tool из асинхронной функции"""
    def sync_wrapper(**kwargs):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        async def run():
            return await func(**kwargs)
        
        return loop.run_until_complete(run())
    
    sync_wrapper.__name__ = name
    sync_wrapper.__doc__ = description
    return Tool(sync_wrapper)

def init_dspy_agent(mcp_server):
    """Инициализация DSPy агента с инструментами Zendriver"""
    if not DSPY_AVAILABLE or not mcp_server:
        return None
    
    AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
    if not AGNES_API_KEY:
        logger.warning("⚠️ AGNES_API_KEY не задан")
        return None
    
    try:
        tools = [
            create_tool(mcp_server.navigate, "navigate", "Перейти на URL"),
            create_tool(mcp_server.screenshot, "screenshot", "Сделать скриншот"),
            create_tool(mcp_server.get_text, "get_text", "Получить текст страницы"),
            create_tool(mcp_server.get_html, "get_html", "Получить HTML страницы"),
            create_tool(mcp_server.click, "click", "Кликнуть по элементу (CSS селектор)"),
            create_tool(mcp_server.type_text, "type_text", "Ввести текст в поле (CSS селектор)"),
            create_tool(mcp_server.find_by_text, "find_by_text", "Найти элемент по тексту"),
            create_tool(mcp_server.get_title, "get_title", "Получить заголовок страницы"),
            create_tool(mcp_server.get_url, "get_url", "Получить текущий URL"),
            create_tool(mcp_server.scroll, "scroll", "Прокрутить страницу"),
            create_tool(mcp_server.solve_turnstile, "solve_turnstile", "Обойти Cloudflare Turnstile"),
            create_tool(mcp_server.get_cookies, "get_cookies", "Получить все куки"),
            create_tool(mcp_server.set_cookies, "set_cookies", "Установить куки из JSON"),
        ]
        
        lm = AgnesLM(
            api_key=AGNES_API_KEY,
            temperature=0.3,
            max_tokens=2000
        )
        
        settings.configure(lm=lm)
        logger.info("✅ DSPy настроен с AgnesLM")
        
        agent = ReActV2(
            signature=BrowserTask,
            tools=tools,
            max_iters=10,
        )
        logger.info(f"✅ DSPy агент создан с {len(tools)} инструментами")
        return agent
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации DSPy: {e}")
        return None

def run_agent(agent, question: str) -> str:
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
# TELEGRAM КОМАНДЫ
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ **Zendriver + DSPy**\n\n"
        "Команды:\n"
        "/start_zd - запустить Zendriver\n"
        "/stop_zd - остановить Zendriver\n"
        "/check - проверить маскировку\n"
        "/screen <url> - сделать скриншот\n"
        "/dspy <задача> - задать вопрос агенту\n"
        "/diag - диагностика"
    )

async def start_zd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Запускаю Zendriver...")
    
    if not ZENDRIVER_AVAILABLE:
        await update.message.reply_text("❌ Zendriver не установлен!")
        return
    
    try:
        # Создаём и запускаем MCP сервер
        mcp = ZendriverMCP()
        await mcp.start(headless=True)
        
        # Сохраняем в bot_data
        context.bot_data['mcp_server'] = mcp
        
        # Инициализируем DSPy агента
        if DSPY_AVAILABLE:
            agent = init_dspy_agent(mcp)
            context.bot_data['dspy_agent'] = agent
        
        await update.message.reply_text(
            f"✅ **Zendriver запущен!**\n\n"
            f"🔌 CDP: http://127.0.0.1:9222\n"
            f"🧠 DSPy: {'✅ Активен' if context.bot_data.get('dspy_agent') else '❌ Отключен'}\n\n"
            f"📋 Команды:\n"
            f"/screen <url> - сделать скриншот\n"
            f"/dspy <задача> - AI-агент\n"
            f"/check - проверить маскировку\n"
            f"/diag - диагностика"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def stop_zd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Останавливаю Zendriver...")
    
    mcp = context.bot_data.get('mcp_server')
    if mcp:
        await mcp.stop()
        context.bot_data['mcp_server'] = None
        context.bot_data['dspy_agent'] = None
        await update.message.reply_text("✅ Zendriver остановлен")
    else:
        await update.message.reply_text("ℹ️ Zendriver не запущен")

async def check_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Проверяю маскировку...")
    
    mcp = context.bot_data.get('mcp_server')
    if not mcp or not mcp.is_ready:
        await update.message.reply_text("❌ Сначала запусти Zendriver: /start_zd")
        return
    
    try:
        await mcp.navigate("https://bot.sannysoft.com")
        await asyncio.sleep(2)
        
        webdriver = await mcp.evaluate("navigator.webdriver")
        
        if webdriver is None or webdriver is False:
            verdict = "✅ **Браузер НЕОТЛИЧИМ!** 🎉"
        else:
            verdict = "⚠️ **Браузер как бот**"
        
        result = await mcp.screenshot()
        if result and result.startswith("✅"):
            filename = result.split(": ")[-1]
            if os.path.exists(filename):
                with open(filename, 'rb') as f:
                    await update.message.reply_photo(
                        photo=f,
                        caption=f"📸 Проверка маскировки"
                    )
        
        await update.message.reply_text(
            f"🔍 **Результат**\n\n"
            f"{verdict}\n"
            f"• navigator.webdriver: `{webdriver}`\n\n"
            f"💡 `None` или `false` — идеально!"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def screen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи URL!\nПример: `/screen https://example.com`")
        return
    
    url = context.args[0]
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    await update.message.reply_text(f"🔄 Открываю `{url}`...")
    
    mcp = context.bot_data.get('mcp_server')
    if not mcp or not mcp.is_ready:
        await update.message.reply_text("❌ Сначала запусти Zendriver: /start_zd")
        return
    
    try:
        await mcp.navigate(url)
        result = await mcp.screenshot()
        
        files = glob.glob("screenshot_*.png")
        if files:
            latest = max(files, key=os.path.getctime)
            with open(latest, 'rb') as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=f"📸 **Скриншот:** `{url}`"
                )
            title = await mcp.get_title()
            await update.message.reply_text(f"✅ **Готово!**\n\n{title}")
        else:
            await update.message.reply_text("❌ Не удалось сохранить скриншот")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🧠 **DSPy Agent**\n\n"
            "Доступные инструменты:\n"
            "• navigate - перейти на URL\n"
            "• screenshot - сделать скриншот\n"
            "• get_text / get_html - получить контент\n"
            "• click - кликнуть по элементу\n"
            "• type_text - ввести текст\n"
            "• find_by_text - найти по тексту\n"
            "• solve_turnstile - обойти Cloudflare\n"
            "• get_cookies / set_cookies - работа с куками\n\n"
            "Пример: `/dspy открой x.com и покажи заголовок`"
        )
        return
    
    mcp = context.bot_data.get('mcp_server')
    if not mcp or not mcp.is_ready:
        await update.message.reply_text("❌ Сначала запусти Zendriver: /start_zd")
        return
    
    agent = context.bot_data.get('dspy_agent')
    if not agent:
        await update.message.reply_text("❌ DSPy агент не инициализирован!\nПроверь AGNES_API_KEY")
        return
    
    user_query = " ".join(context.args)
    username = update.effective_user.username or "unknown"
    logger.info(f"👤 {username} DSPy запрос: {user_query}")
    
    status_msg = await update.message.reply_text("🧠 Думаю...")
    
    try:
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(None, run_agent, agent, user_query)
        
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
    mcp = context.bot_data.get('mcp_server')
    agent = context.bot_data.get('dspy_agent')
    
    report = f"📊 **Диагностика**\n\n"
    report += f"• Zendriver: {'✅' if ZENDRIVER_AVAILABLE else '❌'}\n"
    report += f"• DSPy: {'✅' if DSPY_AVAILABLE else '❌'}\n"
    report += f"• Браузер: {'✅' if mcp and mcp.is_ready else '❌'}\n"
    report += f"• Агент: {'✅' if agent else '❌'}\n"
    report += f"• AGNES_API_KEY: {'✅' if os.environ.get('AGNES_API_KEY') else '❌'}\n"
    
    if mcp and mcp.is_ready and mcp.page:
        try:
            title = await mcp.evaluate("document.title")
            report += f"• Текущая страница: {title}\n"
        except Exception as e:
            report += f"• Текущая страница: ❌ {str(e)[:50]}\n"
    
    await update.message.reply_text(report)

# ============================================
# ЗАПУСК
# ============================================

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("start_zd", start_zd))
    app.add_handler(CommandHandler("stop_zd", stop_zd))
    app.add_handler(CommandHandler("check", check_browser))
    app.add_handler(CommandHandler("screen", screen_command))
    app.add_handler(CommandHandler("dspy", dspy_command))
    app.add_handler(CommandHandler("diag", diag))
    
    logger.info("🤖 Бот запущен!")
    logger.info("📋 Команды: /start_zd, /stop_zd, /check, /screen, /dspy, /diag")
    app.run_polling()

if __name__ == "__main__":
    main()