import os
import sys
import asyncio
import logging
import json
import io
import random
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
    logger.error("❌ Zendriver не установлен! Установи: pip install zendriver")

# ============================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ============================================

browser_instance = None
page_instance = None
cdp_url = "http://127.0.0.1:9222"

# ============================================
# КЛАСС ZENDRIVER MCP СЕРВЕР
# ============================================

class ZendriverMCP:
    """MCP-сервер для Zendriver с 96 инструментами"""
    
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
    
    # ============================================================
    # ИНСТРУМЕНТЫ ДЛЯ MCP
    # ============================================================
    
    async def navigate(self, url: str) -> str:
        """Перейти на URL"""
        if not self.is_ready:
            return "❌ Браузер не запущен"
        try:
            self.page = await self.browser.get(url)
            await asyncio.sleep(random.uniform(1, 3))
            return f"✅ Перешел на {url}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def screenshot(self, filename: str = None) -> str:
        """Сделать скриншот"""
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
        """Получить весь текст страницы"""
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            content = await self.page.get_content()
            return content[:5000] if content else "❌ Нет текста"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def get_html(self) -> str:
        """Получить HTML страницы"""
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            html = await self.page.execute_script("document.documentElement.outerHTML")
            return html[:5000] if html else "❌ Нет HTML"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def click(self, selector: str) -> str:
        """Кликнуть по элементу"""
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            element = await self.page.find(selector).one()
            await element.click()
            return f"✅ Клик по {selector}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def type_text(self, selector: str, text: str) -> str:
        """Ввести текст в поле"""
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            element = await self.page.find(selector).one()
            await element.type_text(text)
            return f"✅ Введено: {text[:20]}..."
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def find_by_text(self, text: str) -> str:
        """Найти элемент по тексту"""
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            element = await self.page.find(text).one()
            return f"✅ Найден элемент: {await element.text()}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def get_title(self) -> str:
        """Получить заголовок страницы"""
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            title = await self.page.execute_script("document.title")
            return f"✅ Заголовок: {title}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def get_url(self) -> str:
        """Получить текущий URL"""
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            return f"✅ URL: {self.page.url}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def scroll(self, dx: int = 0, dy: int = 300) -> str:
        """Прокрутить страницу"""
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            await self.page.execute_script(f"window.scrollBy({dx}, {dy})")
            return f"✅ Прокрутка на ({dx}, {dy})"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def solve_turnstile(self) -> str:
        """Обойти Cloudflare Turnstile"""
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            # В Zendriver есть встроенный решатель
            result = await self.page.solve_turnstile()
            return "✅ Turnstile решён" if result else "⚠️ Turnstile не найден"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def get_cookies(self) -> str:
        """Получить все куки"""
        if not self.is_ready or not self.page:
            return "❌ Браузер или страница не активны"
        try:
            cookies = await self.browser.cookies.get_all()
            return f"✅ Куки: {cookies}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def set_cookies(self, cookies_json: str) -> str:
        """Установить куки из JSON"""
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
# DSPy ИНТЕГРАЦИЯ С MCP
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

# ============================================
# СОЗДАНИЕ АГЕНТА
# ============================================

class BrowserTask(Signature):
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Ответ с использованием Zendriver Browser")

def create_browser_agent(tools, max_iters=10):
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
    api_key = api_key or os.environ.get("AGNES_API_KEY")
    
    if not api_key:
        logger.warning("⚠️ AGNES_API_KEY не задан")
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

# ============================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ============================================

mcp_server = None
dspy_agent = None
dspy_lm = None

# ============================================
# ИНИЦИАЛИЗАЦИЯ MCP + DSPy
# ============================================

def init_dspy_agent():
    global dspy_agent, dspy_lm, mcp_server
    
    if not DSPY_AVAILABLE:
        logger.warning("⚠️ DSPy не доступен")
        return
    
    if not ZENDRIVER_AVAILABLE:
        logger.warning("⚠️ Zendriver не доступен")
        return
    
    AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
    if not AGNES_API_KEY:
        logger.warning("⚠️ AGNES_API_KEY не задан")
        return
    
    try:
        # Создаем MCP-сервер
        mcp_server = ZendriverMCP()
        
        # Создаем инструменты из методов MCP-сервера
        def make_tool(func_name: str, description: str):
            def tool_func(**kwargs):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                async def run():
                    func = getattr(mcp_server, func_name)
                    return await func(**kwargs)
                
                return loop.run_until_complete(run())
            
            tool_func.__name__ = func_name
            tool_func.__doc__ = description
            return tool_func
        
        tools = [
            Tool(make_tool("navigate", "Перейти на URL")),
            Tool(make_tool("screenshot", "Сделать скриншот")),
            Tool(make_tool("get_text", "Получить текст страницы")),
            Tool(make_tool("get_html", "Получить HTML страницы")),
            Tool(make_tool("click", "Кликнуть по элементу (CSS селектор)")),
            Tool(make_tool("type_text", "Ввести текст в поле (CSS селектор)")),
            Tool(make_tool("find_by_text", "Найти элемент по тексту")),
            Tool(make_tool("get_title", "Получить заголовок страницы")),
            Tool(make_tool("get_url", "Получить текущий URL")),
            Tool(make_tool("scroll", "Прокрутить страницу")),
            Tool(make_tool("solve_turnstile", "Обойти Cloudflare Turnstile")),
            Tool(make_tool("get_cookies", "Получить все куки")),
            Tool(make_tool("set_cookies", "Установить куки из JSON")),
        ]
        
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
        logger.error(f"❌ Ошибка инициализации: {e}")
        dspy_agent = None

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
        "/check - проверить маскировку\n"
        "/screen <url> - сделать скриншот\n"
        "/dspy <задача> - задать вопрос агенту\n"
        "/dspy_log - скачать лог DSPy\n"
        "/diag - диагностика"
    )

async def start_zd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global mcp_server, dspy_agent
    await update.message.reply_text("🔄 Запускаю Zendriver...")
    
    if not ZENDRIVER_AVAILABLE:
        await update.message.reply_text("❌ Zendriver не установлен!")
        return
    
    try:
        if mcp_server and mcp_server.is_ready:
            await mcp_server.stop()
        
        mcp_server = ZendriverMCP()
        await mcp_server.start(headless=True)
        
        if DSPY_AVAILABLE:
            await update.message.reply_text("🧠 Инициализирую DSPy агента...")
            init_dspy_agent()
        
        await update.message.reply_text(
            f"✅ **Zendriver запущен!**\n\n"
            f"🔌 CDP: {cdp_url}\n"
            f"🧠 DSPy: {'✅ Активен' if dspy_agent else '❌ Отключен'}\n\n"
            f"📋 Команды:\n"
            f"/screen <url> - сделать скриншот\n"
            f"/dspy <задача> - AI-агент\n"
            f"/dspy_log - скачать лог"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def check_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Проверяю маскировку...")
    
    if not mcp_server or not mcp_server.is_ready:
        await update.message.reply_text("❌ Сначала запусти Zendriver: /start_zd")
        return
    
    try:
        await mcp_server.navigate("https://bot.sannysoft.com")
        result = await mcp_server.get_text()
        
        # Проверяем webdriver
        webdriver = await mcp_server.page.execute_script("navigator.webdriver")
        
        if webdriver is None or webdriver is False:
            verdict = "✅ **Браузер НЕОТЛИЧИМ!** 🎉"
        else:
            verdict = "⚠️ **Браузер как бот**"
        
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
    
    if not mcp_server or not mcp_server.is_ready:
        await update.message.reply_text("❌ Сначала запусти Zendriver: /start_zd")
        return
    
    try:
        await mcp_server.navigate(url)
        result = await mcp_server.screenshot()
        
        # Находим файл скриншота
        import glob
        files = glob.glob("screenshot_*.png")
        if files:
            latest = max(files, key=os.path.getctime)
            with open(latest, 'rb') as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=f"📸 **Скриншот:** `{url}`"
                )
            info = await mcp_server.get_title()
            await update.message.reply_text(f"✅ **Готово!**\n\n{info}")
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
    
    if not mcp_server or not mcp_server.is_ready:
        await update.message.reply_text("❌ Сначала запусти Zendriver: /start_zd")
        return
    
    if not DSPY_AVAILABLE:
        await update.message.reply_text("❌ DSPy не установлен!")
        return
    
    if not dspy_agent:
        await update.message.reply_text("❌ DSPy агент не инициализирован!\nПроверь AGNES_API_KEY")
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

async def dspy_log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_file = "dspy.log"
    if not os.path.exists(log_file):
        await update.message.reply_text("📄 Лог DSPy пуст")
        return
    
    try:
        await update.message.reply_document(
            document=open(log_file, "rb"),
            filename="dspy.log",
            caption="📄 Лог DSPy"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = f"📊 **Диагностика**\n\n"
    report += f"• Zendriver: {'✅' if ZENDRIVER_AVAILABLE else '❌'}\n"
    report += f"• DSPy: {'✅' if DSPY_AVAILABLE else '❌'}\n"
    report += f"• Браузер: {'✅' if mcp_server and mcp_server.is_ready else '❌'}\n"
    report += f"• Агент: {'✅' if dspy_agent else '❌'}\n"
    report += f"• AGNES_API_KEY: {'✅' if os.environ.get('AGNES_API_KEY') else '❌'}\n"
    
    if mcp_server and mcp_server.is_ready and mcp_server.page:
        try:
            title = await mcp_server.get_title()
            report += f"• Текущая страница: {title}\n"
        except:
            pass
    
    await update.message.reply_text(report)

# ============================================
# ЗАПУСК
# ============================================

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("start_zd", start_zd))
    app.add_handler(CommandHandler("check", check_browser))
    app.add_handler(CommandHandler("screen", screen_command))
    app.add_handler(CommandHandler("dspy", dspy_command))
    app.add_handler(CommandHandler("dspy_log", dspy_log_command))
    app.add_handler(CommandHandler("diag", diag))
    
    logger.info("🤖 Бот запущен!")
    logger.info("📋 Команды: /start_zd, /check, /screen, /dspy, /dspy_log, /diag")
    app.run_polling()

if __name__ == "__main__":
    main()