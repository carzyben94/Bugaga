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
# ИМПОРТЫ MCP И ZENDRIVER
# ============================================

try:
    import zendriver as zd
    ZENDRIVER_AVAILABLE = True
    logger.info("✅ Zendriver импортирован")
except ImportError:
    ZENDRIVER_AVAILABLE = False
    logger.error("❌ Zendriver не установлен!")

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_AVAILABLE = True
    logger.info("✅ MCP импортирован")
except ImportError:
    MCP_AVAILABLE = False
    logger.error("❌ MCP не установлен!")

# ============================================
# MCP КЛИЕНТ ДЛЯ ZENDRIVER
# ============================================

class ZendriverMCPClient:
    """MCP-клиент для zendriver-mcp"""
    
    def __init__(self):
        self.session = None
        self._client = None
        self._read_stream = None
        self._write_stream = None
        self.is_ready = False
        self.tools = []
    
    async def start(self):
        """Запуск MCP-сервера zendriver-mcp"""
        logger.info("🔄 Запускаю zendriver-mcp через MCP...")
        
        if not MCP_AVAILABLE:
            logger.error("❌ MCP не доступен")
            return False
        
        try:
            # Создаём параметры сервера
            server_params = StdioServerParameters(
                command="zendriver-mcp",
                args=["--headless"]
            )
            
            # Подключаемся к серверу
            self._read_stream, self._write_stream = await stdio_client(server_params)
            self.session = await ClientSession(self._read_stream, self._write_stream)
            
            # Инициализация
            await self.session.initialize()
            
            # Получаем список инструментов
            response = await self.session.list_tools()
            self.tools = response.tools
            self.is_ready = True
            
            logger.info(f"✅ MCP клиент запущен, {len(self.tools)} инструментов")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска MCP: {e}")
            return False
    
    async def stop(self):
        """Остановка MCP-клиента"""
        if self.session:
            await self.session.__aexit__(None, None, None)
            self.is_ready = False
            logger.info("✅ MCP клиент остановлен")
    
    async def call_tool(self, tool_name: str, arguments: dict = None) -> dict:
        """Вызвать инструмент MCP"""
        if not self.is_ready:
            return {"error": "MCP-клиент не готов"}
        
        try:
            result = await self.session.call_tool(tool_name, arguments or {})
            return result.content[0].text if result.content else {}
        except Exception as e:
            logger.error(f"❌ Ошибка вызова {tool_name}: {e}")
            return {"error": str(e)}
    
    # ============================================================
    # ОСНОВНЫЕ ИНСТРУМЕНТЫ
    # ============================================================
    
    async def navigate(self, url: str) -> dict:
        return await self.call_tool("navigate", {"url": url})
    
    async def screenshot(self, path: str = None) -> dict:
        args = {}
        if path:
            args["path"] = path
        return await self.call_tool("screenshot", args)
    
    async def get_text(self) -> dict:
        return await self.call_tool("get_text", {})
    
    async def get_html(self) -> dict:
        return await self.call_tool("get_html", {})
    
    async def click(self, selector: str) -> dict:
        return await self.call_tool("click", {"selector": selector})
    
    async def type_text(self, selector: str, text: str) -> dict:
        return await self.call_tool("type", {"selector": selector, "text": text})
    
    async def find_element(self, text: str) -> dict:
        return await self.call_tool("find", {"text": text})
    
    async def get_title(self) -> dict:
        return await self.call_tool("get_title", {})
    
    async def get_url(self) -> dict:
        return await self.call_tool("get_url", {})
    
    async def scroll(self, dx: int = 0, dy: int = 300) -> dict:
        return await self.call_tool("scroll", {"dx": dx, "dy": dy})
    
    async def cloudflare_bypass(self) -> dict:
        return await self.call_tool("cloudflare_bypass", {})
    
    async def get_cookies(self) -> dict:
        return await self.call_tool("list_cookies", {})
    
    async def set_cookies(self, cookies: list) -> dict:
        return await self.call_tool("import_cookies", {"cookies": cookies})
    
    async def clear_cookies(self) -> dict:
        return await self.call_tool("clear_cookies", {})
    
    async def human_click(self, selector: str) -> dict:
        return await self.call_tool("human_click", {"selector": selector})
    
    async def human_type(self, selector: str, text: str) -> dict:
        return await self.call_tool("human_type", {"selector": selector, "text": text})
    
    async def ax_snapshot(self) -> dict:
        return await self.call_tool("ax_snapshot", {})
    
    async def console_logs(self) -> dict:
        return await self.call_tool("console_logs", {})
    
    async def wait_for_request(self, url_pattern: str, timeout: int = 10) -> dict:
        return await self.call_tool("wait_for_request", {"url": url_pattern, "timeout": timeout})

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
    Ты агент с доступом к невидимому браузеру через Zendriver MCP.
    
    ДОСТУПНЫЕ ИНСТРУМЕНТЫ:
    • navigate(url) — перейти на URL
    • screenshot(path) — сделать скриншот
    • get_text() — получить текст страницы
    • get_html() — получить HTML
    • click(selector) — кликнуть по элементу
    • type(selector, text) — ввести текст
    • find(text) — найти элемент по тексту
    • get_title() — заголовок страницы
    • get_url() — текущий URL
    • scroll(dx, dy) — прокрутка
    • cloudflare_bypass() — обойти Cloudflare
    • human_click(selector) — клик как человек
    • human_type(selector, text) — ввод как человек
    • ax_snapshot() — Accessibility Tree
    • list_cookies() / import_cookies(cookies) / clear_cookies()
    • console_logs() — логи консоли
    • wait_for_request(url, timeout) — ждать сетевой запрос
    
    ПРАВИЛА:
    1. Сначала navigate(url)
    2. Проверяй get_title() или get_text()
    3. Используй human_click и human_type для маскировки
    """
    
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Результат выполнения")

# ============================================
# СОЗДАНИЕ АГЕНТА
# ============================================

def create_tool(client, method_name: str, description: str):
    """Создать dspy.Tool из метода MCP-клиента"""
    def sync_wrapper(**kwargs):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        async def run():
            result = await getattr(client, method_name)(**kwargs)
            if isinstance(result, dict):
                if "error" in result:
                    return f"❌ Ошибка: {result['error']}"
                return str(result)
            return str(result)
        
        return loop.run_until_complete(run())
    
    sync_wrapper.__name__ = method_name
    sync_wrapper.__doc__ = description
    return Tool(sync_wrapper)

def init_dspy_agent(client):
    """Инициализация DSPy агента с инструментами MCP"""
    if not DSPY_AVAILABLE or not client:
        return None
    
    AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
    if not AGNES_API_KEY:
        logger.warning("⚠️ AGNES_API_KEY не задан")
        return None
    
    try:
        # Список инструментов из MCP
        tool_names = [
            ("navigate", "Перейти на URL"),
            ("screenshot", "Сделать скриншот"),
            ("get_text", "Получить текст страницы"),
            ("get_html", "Получить HTML страницы"),
            ("click", "Кликнуть по элементу"),
            ("type_text", "Ввести текст"),
            ("find_element", "Найти элемент по тексту"),
            ("get_title", "Получить заголовок"),
            ("get_url", "Получить текущий URL"),
            ("scroll", "Прокрутить страницу"),
            ("cloudflare_bypass", "Обойти Cloudflare Turnstile"),
            ("human_click", "Человеческий клик"),
            ("human_type", "Человеческий ввод"),
            ("ax_snapshot", "Accessibility Tree"),
            ("get_cookies", "Получить куки"),
            ("set_cookies", "Установить куки"),
            ("clear_cookies", "Очистить куки"),
            ("console_logs", "Логи консоли"),
            ("wait_for_request", "Ожидание сетевого запроса"),
        ]
        
        tools = []
        for name, desc in tool_names:
            if hasattr(client, name):
                tools.append(create_tool(client, name, desc))
        
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

# Глобальные переменные
mcp_client = None
dspy_agent = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ **Zendriver MCP + DSPy**\n\n"
        "Команды:\n"
        "/start_zd - запустить Zendriver MCP\n"
        "/stop_zd - остановить\n"
        "/check - проверить маскировку\n"
        "/screen <url> - сделать скриншот\n"
        "/dspy <задача> - задать вопрос агенту\n"
        "/diag - диагностика"
    )

async def start_zd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global mcp_client, dspy_agent
    await update.message.reply_text("🔄 Запускаю Zendriver MCP...")
    
    if not MCP_AVAILABLE:
        await update.message.reply_text("❌ MCP не установлен!\nУстанови: pip install mcp")
        return
    
    try:
        mcp_client = ZendriverMCPClient()
        success = await mcp_client.start()
        
        if not success:
            await update.message.reply_text("❌ Не удалось запустить MCP-сервер")
            return
        
        context.bot_data['mcp_client'] = mcp_client
        
        if DSPY_AVAILABLE:
            await update.message.reply_text("🧠 Инициализирую DSPy агента...")
            dspy_agent = init_dspy_agent(mcp_client)
            context.bot_data['dspy_agent'] = dspy_agent
        
        await update.message.reply_text(
            f"✅ **Zendriver MCP запущен!**\n\n"
            f"🔧 Инструментов: {len(mcp_client.tools)}\n"
            f"🧠 DSPy: {'✅ Активен' if dspy_agent else '❌ Отключен'}\n\n"
            f"📋 Команды:\n"
            f"/screen <url> - скриншот\n"
            f"/dspy <задача> - AI-агент\n"
            f"/check - проверка маскировки"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def stop_zd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global mcp_client
    await update.message.reply_text("🔄 Останавливаю Zendriver MCP...")
    
    if mcp_client:
        await mcp_client.stop()
        mcp_client = None
        context.bot_data['mcp_client'] = None
        context.bot_data['dspy_agent'] = None
        await update.message.reply_text("✅ Zendriver MCP остановлен")
    else:
        await update.message.reply_text("ℹ️ Zendriver MCP не запущен")

async def check_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Проверяю маскировку...")
    
    client = context.bot_data.get('mcp_client')
    if not client or not client.is_ready:
        await update.message.reply_text("❌ Сначала запусти Zendriver: /start_zd")
        return
    
    try:
        await client.navigate("https://bot.sannysoft.com")
        await asyncio.sleep(2)
        
        result = await client.call_tool("evaluate", {"script": "navigator.webdriver"})
        webdriver = result.get("result") if isinstance(result, dict) else result
        
        if webdriver is None or webdriver is False:
            verdict = "✅ **Браузер НЕОТЛИЧИМ!** 🎉"
        else:
            verdict = "⚠️ **Браузер как бот**"
        
        timestamp = int(time.time())
        filename = f"screenshot_{timestamp}.png"
        await client.screenshot(filename)
        
        if os.path.exists(filename):
            with open(filename, 'rb') as f:
                await update.message.reply_photo(photo=f, caption="📸 Проверка маскировки")
        
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
    
    client = context.bot_data.get('mcp_client')
    if not client or not client.is_ready:
        await update.message.reply_text("❌ Сначала запусти Zendriver: /start_zd")
        return
    
    try:
        await client.navigate(url)
        await asyncio.sleep(2)
        
        timestamp = int(time.time())
        filename = f"screenshot_{timestamp}.png"
        await client.screenshot(filename)
        
        if os.path.exists(filename):
            with open(filename, 'rb') as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=f"📸 **Скриншот:** `{url}`"
                )
            
            title_result = await client.get_title()
            title = title_result.get("result", "N/A") if isinstance(title_result, dict) else title_result
            await update.message.reply_text(f"✅ **Готово!**\n\n📌 Title: {title}")
        else:
            await update.message.reply_text("❌ Не удалось сохранить скриншот")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🧠 **DSPy Agent**\n\n"
            "Доступные инструменты:\n"
            "• navigate, screenshot, get_text, get_html\n"
            "• click, type_text, find_element\n"
            "• get_title, get_url, scroll\n"
            "• cloudflare_bypass, human_click, human_type\n"
            "• ax_snapshot, get_cookies, set_cookies, clear_cookies\n"
            "• console_logs, wait_for_request\n\n"
            "Пример: `/dspy открой x.com и покажи заголовок`"
        )
        return
    
    client = context.bot_data.get('mcp_client')
    if not client or not client.is_ready:
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
    client = context.bot_data.get('mcp_client')
    agent = context.bot_data.get('dspy_agent')
    
    report = f"📊 **Диагностика**\n\n"
    report += f"• Zendriver: {'✅' if ZENDRIVER_AVAILABLE else '❌'}\n"
    report += f"• MCP: {'✅' if MCP_AVAILABLE else '❌'}\n"
    report += f"• MCP клиент: {'✅' if client and client.is_ready else '❌'}\n"
    report += f"• DSPy: {'✅' if DSPY_AVAILABLE else '❌'}\n"
    report += f"• Агент: {'✅' if agent else '❌'}\n"
    report += f"• AGNES_API_KEY: {'✅' if os.environ.get('AGNES_API_KEY') else '❌'}\n"
    
    if client and client.is_ready:
        report += f"• Инструментов: {len(client.tools)}\n"
    
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