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
# 5. ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР БРАУЗЕРА
# ============================================================

browser_instance = None
page_instance = None
dspy_agent_instance = None
loop_for_browser = None

# ============================================================
# 6. СОЗДАНИЕ DSPy АГЕНТА С РЕАЛЬНЫМ БРАУЗЕРОМ
# ============================================================

def get_or_create_loop():
    """Получить или создать event loop"""
    global loop_for_browser
    try:
        loop = asyncio.get_running_loop()
        return loop
    except RuntimeError:
        if loop_for_browser is None or loop_for_browser.is_closed():
            loop_for_browser = asyncio.new_event_loop()
            asyncio.set_event_loop(loop_for_browser)
        return loop_for_browser

def run_async(coro):
    """Выполнить асинхронную функцию в синхронном контексте"""
    loop = get_or_create_loop()
    if loop.is_running():
        # Если loop уже запущен, создаём новый для этого вызова
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
            # Восстанавливаем старый loop
            asyncio.set_event_loop(loop)
    else:
        return loop.run_until_complete(coro)

async def init_browser_async():
    """Асинхронная инициализация браузера"""
    global browser_instance, page_instance, dspy_agent_instance
    
    try:
        # Запускаем браузер
        browser_instance = await launch_async(
            headless=True,
            args=["--fingerprint"]
        )
        page_instance = await browser_instance.new_page()
        logger.info("✅ CloakBrowser запущен")
        
        # Создаём инструменты
        tools = create_tools()
        
        # Инициализируем DSPy
        api_key = os.environ.get("AGNES_API_KEY")
        if api_key:
            lm = AgnesLM(api_key=api_key, temperature=0.3, max_tokens=2000)
            settings.configure(lm=lm)
            
            dspy_agent_instance = ReActV2(
                signature=BrowserTask,
                tools=tools,
                max_iters=10,
            )
            logger.info(f"✅ DSPy агент создан с {len(tools)} инструментами")
        else:
            logger.warning("⚠️ AGNES_API_KEY не задан")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации браузера: {e}")
        return False

def init_browser():
    """Синхронная обёртка для инициализации браузера"""
    loop = get_or_create_loop()
    if loop.is_running():
        # Если loop запущен, создаём задачу
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, init_browser_async())
            return future.result()
    else:
        return loop.run_until_complete(init_browser_async())

def create_tools():
    """Создать инструменты с реальным браузером"""
    tools = []
    
    def tool_goto_url(url: str) -> str:
        """Перейти на URL"""
        try:
            result = run_async(page_instance.goto(url, wait_until="networkidle"))
            return f"✅ Перешел на {url}"
        except Exception as e:
            return f"❌ Ошибка перехода: {e}"
    tools.append(Tool(tool_goto_url))
    
    def tool_screenshot() -> str:
        """Сделать скриншот"""
        try:
            screenshot = run_async(page_instance.screenshot())
            import time
            filename = f"/app/screenshots/dspy_{int(time.time())}.png"
            os.makedirs("/app/screenshots", exist_ok=True)
            with open(filename, "wb") as f:
                f.write(screenshot)
            return f"✅ Скриншот сохранён: {filename}"
        except Exception as e:
            return f"❌ Ошибка скриншота: {e}"
    tools.append(Tool(tool_screenshot))
    
    def tool_get_text() -> str:
        """Получить весь текст страницы"""
        try:
            text = run_async(page_instance.content())
            import re
            clean_text = re.sub(r'<[^>]+>', ' ', text)
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            if len(clean_text) > 3000:
                clean_text = clean_text[:3000] + "..."
            return f"✅ Текст страницы:\n{clean_text}" if clean_text else "❌ Текст не найден"
        except Exception as e:
            return f"❌ Ошибка получения текста: {e}"
    tools.append(Tool(tool_get_text))
    
    def tool_get_title() -> str:
        """Получить заголовок страницы"""
        try:
            title = run_async(page_instance.title())
            return f"✅ Заголовок: {title}" if title else "❌ Заголовок не найден"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_get_title))
    
    def tool_js(expression: str) -> str:
        """Выполнить JavaScript на странице"""
        try:
            result = run_async(page_instance.evaluate(expression))
            return f"✅ JS выполнен: {result}" if result is not None else "✅ JS выполнен (нет результата)"
        except Exception as e:
            return f"❌ Ошибка JS: {e}"
    tools.append(Tool(tool_js))
    
    return tools

def run_dspy_agent(question: str) -> str:
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
# 7. ТЕЛЕГРАМ БОТ
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

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
    global dspy_agent_instance
    
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
    
    if not dspy_agent_instance:
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
        # Выполняем задачу через DSPy агента в отдельном потоке
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(
            None, run_dspy_agent, user_query
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
# 8. ЗАПУСК
# ============================================================

def main():
    # Инициализируем браузер и DSPy (синхронно)
    logger.info("🚀 Инициализация браузера и DSPy...")
    init_browser()
    
    # Создаём Telegram бота
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("version", version))
    app.add_handler(CommandHandler("dspy", dspy_command))
    
    logger.info("🚀 Бот запущен!")
    logger.info(f"🧠 DSPy статус: {'✅ Активен' if dspy_agent_instance else '❌ Отключен'}")
    logger.info(f"🌐 CloakBrowser: {'✅ Запущен' if browser_instance else '❌ Не запущен'}")
    
    # Запускаем бота (он сам создаст свой event loop)
    app.run_polling()

if __name__ == "__main__":
    main()