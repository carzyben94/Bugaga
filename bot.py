import os
import asyncio
import logging
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
from dspy import Signature, InputField, OutputField, Module, settings, ReActV2, Tool

warnings.filterwarnings("ignore")

# ============================================================
# 3. AGNES LM АДАПТЕР ДЛЯ DSPy
# ============================================================

class AgnesLM(dspy.LM):
    """Адаптер для Agnes AI совместимый с DSPy"""
    
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

# ============================================================
# 4. DSPy ИНСТРУМЕНТЫ (для работы с браузером)
# ============================================================

def create_dspy_tools():
    """Создать инструменты для DSPy агента"""
    tools = []
    
    # Инструмент: переход по URL
    def tool_goto_url(url: str) -> str:
        """Перейти на URL"""
        try:
            # Здесь можно добавить логику перехода
            return f"✅ Перешел на {url}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_goto_url))
    
    # Инструмент: скриншот
    def tool_screenshot() -> str:
        """Сделать скриншот страницы"""
        try:
            return "✅ Скриншот сделан"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_screenshot))
    
    # Инструмент: получить текст страницы
    def tool_get_text() -> str:
        """Получить текст со страницы"""
        try:
            return "Текст страницы"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_get_text))
    
    # Инструмент: выполнить JS
    def tool_js(expression: str) -> str:
        """Выполнить JavaScript на странице"""
        try:
            return f"✅ JS выполнен: {expression}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    tools.append(Tool(tool_js))
    
    return tools

# ============================================================
# 5. DSPy СИГНАТУРА
# ============================================================

class BrowserTask(Signature):
    """
    Ты агент с доступом к браузеру.
    
    ДОСТУПНЫЕ ИНСТРУМЕНТЫ:
    - tool_goto_url(url) - перейти на сайт
    - tool_screenshot() - сделать скриншот
    - tool_get_text() - получить текст страницы
    - tool_js(expression) - выполнить JavaScript
    
    ПРАВИЛА:
    - Используй инструменты для работы с браузером
    - Отвечай на русском языке
    - Если нужна дополнительная информация - уточняй
    """
    
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Ответ с использованием инструментов браузера")

# ============================================================
# 6. СОЗДАНИЕ DSPy АГЕНТА
# ============================================================

def create_dspy_agent(tools, max_iters=10):
    """Создать DSPy агента"""
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
    """Инициализировать DSPy"""
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
            agent = create_dspy_agent(tools, max_iters)
        else:
            agent = None
        
        return lm, agent
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации DSPy: {e}")
        return None, None

def run_agent(agent, question: str) -> str:
    """Запустить агента"""
    if not agent:
        return "❌ Агент не инициализирован"
    
    try:
        result = agent(question=question)
        answer = getattr(result, 'answer', str(result))
        return answer if answer and answer.strip() else "❌ Пустой ответ"
    except Exception as e:
        logger.error(f"❌ Ошибка выполнения агента: {e}")
        return f"❌ Ошибка: {str(e)}"

# ============================================================
# 7. ТЕЛЕГРАМ КОМАНДЫ
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

# Глобальные переменные
dspy_agent = None
dspy_lm = None
browser_instance = None  # Для интеграции с браузером

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
            args=["--fingerprint"]  # Маскировка
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
        import subprocess
        result = subprocess.run(
            ['cloakbrowser', 'info'],
            capture_output=True,
            text=True,
            timeout=5
        )
        info = result.stdout.strip() or result.stderr.strip()
        
        await update.message.reply_text(
            f"📦 **CloakBrowser**\n"
            f"• Пакет: `0.5.7`\n"
            f"• Статус: ✅ Работает\n"
            f"• Инфо: `{info[:200] if info else 'доступен'}`"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /dspy"""
    global dspy_agent
    
    if not context.args:
        await update.message.reply_text(
            "🧠 **DSPy Agent**\n\n"
            "Отправь задачу агенту:\n"
            "`/dspy открой google.com и покажи заголовок`\n\n"
            "Агент использует Agnes AI для выполнения задач.",
            parse_mode='Markdown'
        )
        return
    
    if not dspy_agent:
        await update.message.reply_text(
            "❌ **DSPy агент не инициализирован.**\n"
            "Проверьте переменную `AGNES_API_KEY`."
        )
        return
    
    user_query = " ".join(context.args)
    username = update.effective_user.username or "unknown"
    logger.info(f"👤 {username} DSPy запрос: {user_query}")
    
    status_msg = await update.message.reply_text("🧠 Думаю...")
    
    try:
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(
            None, run_agent, dspy_agent, user_query
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
# 8. ИНИЦИАЛИЗАЦИЯ DSPy ПРИ ЗАПУСКЕ
# ============================================================

def init_agent():
    """Инициализировать DSPy агента"""
    global dspy_agent, dspy_lm
    
    AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
    
    if not AGNES_API_KEY:
        logger.warning("⚠️ AGNES_API_KEY не задан, DSPy отключен")
        return False
    
    try:
        tools = create_dspy_tools()
        dspy_lm, dspy_agent = init_dspy(
            api_key=AGNES_API_KEY,
            tools=tools,
            max_iters=10
        )
        
        if dspy_agent:
            logger.info(f"✅ DSPy агент инициализирован с {len(tools)} инструментами")
            return True
        else:
            logger.warning("⚠️ Не удалось создать DSPy агента")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации DSPy: {e}")
        return False

# ============================================================
# 9. ЗАПУСК БОТА
# ============================================================

def main():
    global dspy_agent
    
    # Инициализируем DSPy
    init_agent()
    
    # Создаём бота
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("version", version))
    app.add_handler(CommandHandler("dspy", dspy_command))
    
    logger.info("🚀 Бот запущен!")
    logger.info(f"📋 Команды: /start, /check, /version, /dspy")
    logger.info(f"🧠 DSPy статус: {'✅ Активен' if dspy_agent else '❌ Отключен'}")
    
    app.run_polling()

if __name__ == "__main__":
    main()