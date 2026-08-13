import os
import asyncio
import logging
import subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.helpers import escape_markdown
from cloakbrowser import launch_async

# ============================================================
# 1. НАСТРОЙКА ЛОГГЕРА
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# 2. ИМПОРТЫ DSPy
# ============================================================

import warnings
import httpx
import dspy
from dspy import Signature, InputField, OutputField, settings, ReActV2, Tool

warnings.filterwarnings("ignore")

# ============================================================
# 3. AGNES LM АДАПТЕР
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
    
    def __call__(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)

# ============================================================
# 4. DSPy СИГНАТУРА
# ============================================================

class BrowserTask(Signature):
    """
    Ты агент с доступом к браузеру.
    
    ДОСТУПНЫЕ ИНСТРУМЕНТЫ:
    - tool_goto_url(url) - перейти на сайт
    - tool_screenshot() - сделать скриншот
    - tool_get_text() - получить весь текст страницы
    - tool_get_title() - получить заголовок страницы
    - tool_js(expression) - выполнить JavaScript
    
    ПРАВИЛА:
    - Сначала всегда открывай страницу через tool_goto_url
    - Потом используй другие инструменты
    - Отвечай понятно и кратко
    """
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Результат выполнения задачи")

# ============================================================
# 5. СОЗДАНИЕ DSPy АГЕНТА С РЕАЛЬНЫМ БРАУЗЕРОМ
# ============================================================

class BrowserAgent:
    def __init__(self):
        self.browser = None
        self.page = None
        self.dspy_agent = None
        self.loop = None
    
    async def init_browser(self):
        """Запустить браузер"""
        self.browser = await launch_async(
            headless=True,
            args=["--fingerprint"]
        )
        self.page = await self.browser.new_page()
        logger.info("✅ CloakBrowser запущен")
        return self.page
    
    def _run_async(self, coro):
        """Выполнить асинхронную функцию в синхронном контексте"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        if loop.is_running():
            # Если цикл уже запущен (Telegram), создаём новый
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            return new_loop.run_until_complete(coro)
        else:
            return loop.run_until_complete(coro)
    
    def create_tools(self):
        """Создать инструменты с реальным браузером"""
        page = self.page
        if not page:
            raise RuntimeError("Браузер не инициализирован")
        
        def tool_goto_url(url: str) -> str:
            """Перейти на URL"""
            try:
                self._run_async(page.goto(url, wait_until="networkidle"))
                return f"✅ Перешел на {url}"
            except Exception as e:
                return f"❌ Ошибка перехода: {e}"
        
        def tool_screenshot() -> str:
            """Сделать скриншот"""
            try:
                screenshot = self._run_async(page.screenshot())
                # Сохраняем в файл
                import time
                filename = f"/app/screenshots/dspy_{int(time.time())}.png"
                os.makedirs("/app/screenshots", exist_ok=True)
                with open(filename, "wb") as f:
                    f.write(screenshot)
                return f"✅ Скриншот сохранён: {filename}"
            except Exception as e:
                return f"❌ Ошибка скриншота: {e}"
        
        def tool_get_text() -> str:
            """Получить весь текст страницы"""
            try:
                text = self._run_async(page.content())
                # Извлекаем только текст из HTML
                import re
                clean_text = re.sub(r'<[^>]+>', ' ', text)
                clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                if len(clean_text) > 3000:
                    clean_text = clean_text[:3000] + "..."
                return f"✅ Текст страницы:\n{clean_text}" if clean_text else "❌ Текст не найден"
            except Exception as e:
                return f"❌ Ошибка получения текста: {e}"
        
        def tool_get_title() -> str:
            """Получить заголовок страницы"""
            try:
                title = self._run_async(page.title())
                return f"✅ Заголовок: {title}" if title else "❌ Заголовок не найден"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_js(expression: str) -> str:
            """Выполнить JavaScript на странице"""
            try:
                result = self._run_async(page.evaluate(expression))
                return f"✅ JS выполнен: {result}" if result is not None else "✅ JS выполнен (нет результата)"
            except Exception as e:
                return f"❌ Ошибка JS: {e}"
        
        return [
            Tool(tool_goto_url),
            Tool(tool_screenshot),
            Tool(tool_get_text),
            Tool(tool_get_title),
            Tool(tool_js),
        ]
    
    def init_dspy(self, max_iters=10):
        """Инициализировать DSPy агента"""
        api_key = os.environ.get("AGNES_API_KEY")
        if not api_key:
            logger.warning("⚠️ AGNES_API_KEY не задан")
            return None
        
        try:
            lm = AgnesLM(api_key=api_key, temperature=0.3, max_tokens=2000)
            settings.configure(lm=lm)
            
            tools = self.create_tools()
            
            self.dspy_agent = ReActV2(
                signature=BrowserTask,
                tools=tools,
                max_iters=max_iters,
            )
            
            logger.info(f"✅ DSPy агент создан с {len(tools)} инструментами")
            return self.dspy_agent
            
        except Exception as e:
            logger.error(f"❌ Ошибка DSPy: {e}")
            return None
    
    def run(self, question: str) -> str:
        """Выполнить задачу"""
        if not self.dspy_agent:
            return "❌ DSPy агент не инициализирован"
        
        try:
            result = self.dspy_agent(question=question)
            answer = getattr(result, 'answer', str(result))
            return answer if answer and answer.strip() else "❌ Пустой ответ"
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения: {e}")
            return f"❌ Ошибка: {str(e)}"
    
    async def close(self):
        """Закрыть браузер"""
        if self.browser:
            await self.browser.close()
            logger.info("✅ Браузер закрыт")

# ============================================================
# 6. ТЕЛЕГРАМ БОТ
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# Глобальный экземпляр
browser_agent = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Команды:\n"
        "/check <url> - проверить сайт\n"
        "/dspy <запрос> - задать вопрос DSPy агенту\n"
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
            f"• Инфо: `{info[:200] if info else 'доступен'}`"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик /dspy с реальным браузером"""
    global browser_agent
    
    if not context.args:
        await update.message.reply_text(
            "🧠 **DSPy Agent**\n\n"
            "Отправь задачу:\n"
            "`/dspy открой google.com и покажи заголовок`\n"
            "`/dspy сделай скриншот example.com`\n"
            "`/dspy перейди на python.org и получи текст`\n\n"
            "Агент сам откроет браузер и выполнит задачу!",
            parse_mode='Markdown'
        )
        return
    
    if not browser_agent or not browser_agent.dspy_agent:
        await update.message.reply_text(
            "❌ **DSPy агент не инициализирован.**\n"
            "Проверьте переменную `AGNES_API_KEY`."
        )
        return
    
    user_query = " ".join(context.args)
    username = update.effective_user.username or "unknown"
    logger.info(f"👤 {username} DSPy: {user_query}")
    
    status_msg = await update.message.reply_text("🧠 Думаю и открываю браузер...")
    
    try:
        # Выполняем задачу через DSPy агента
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(
            None, browser_agent.run, user_query
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
# 7. ИНИЦИАЛИЗАЦИЯ
# ============================================================

async def init_browser_agent():
    """Инициализировать браузер и DSPy агента"""
    global browser_agent
    
    try:
        browser_agent = BrowserAgent()
        
        # Запускаем браузер
        await browser_agent.init_browser()
        
        # Инициализируем DSPy
        browser_agent.init_dspy()
        
        if browser_agent.dspy_agent:
            logger.info("✅ DSPy агент готов к работе")
        else:
            logger.warning("⚠️ DSPy агент не создан")
            
        return browser_agent
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации: {e}")
        return None

# ============================================================
# 8. ЗАПУСК
# ============================================================

def main():
    global browser_agent
    
    # Инициализируем браузер и DSPy (в синхронном контексте)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    browser_agent = loop.run_until_complete(init_browser_agent())
    loop.close()
    
    # Создаём Telegram бота
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("version", version))
    app.add_handler(CommandHandler("dspy", dspy_command))
    
    logger.info("🚀 Бот запущен!")
    logger.info(f"🧠 DSPy статус: {'✅ Активен' if browser_agent and browser_agent.dspy_agent else '❌ Отключен'}")
    logger.info(f"🌐 CloakBrowser: {'✅ Запущен' if browser_agent and browser_agent.browser else '❌ Не запущен'}")
    
    app.run_polling()

if __name__ == "__main__":
    main()