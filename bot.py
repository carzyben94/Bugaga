import os
import logging
import httpx
import re
import asyncio
import concurrent.futures
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import dspy
from dspy import Signature, InputField, OutputField, settings, ReActV2, Tool

# ==================== НАСТРОЙКА ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ==================== ПЕРЕМЕННЫЕ ====================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")

if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не установлен!")

logger.info(f"🔑 AGNES_API_KEY: {'✅ есть' if AGNES_API_KEY else '❌ нет'}")
logger.info(f"🤖 TELEGRAM_BOT_TOKEN: {'✅ есть' if TOKEN else '❌ нет'}")

# ==================== ПРОВЕРКА PLASMATE ====================
try:
    from dspy_plasmate import PlasmateFetchTool
    PLASMATE_AVAILABLE = True
    logger.info("✅ dspy-plasmate импортирован")
except ImportError as e:
    PLASMATE_AVAILABLE = False
    logger.error(f"❌ Ошибка импорта dspy-plasmate: {e}")

# ==================== ИНИЦИАЛИЗАЦИЯ PLASMATE ====================
plasmate_tool = None

if PLASMATE_AVAILABLE:
    try:
        # Правильная инициализация — БЕЗ аргументов
        plasmate_tool = PlasmateFetchTool()
        logger.info("✅ Plasmate подключен")
        
        # Тест
        test_result = plasmate_tool("https://example.com")
        logger.info(f"🔍 Тест Plasmate: {type(test_result)}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Plasmate: {e}")
        PLASMATE_AVAILABLE = False

# ==================== ИНСТРУМЕНТЫ ДЛЯ DSPy ====================

def fetch_page(url: str) -> str:
    """Открыть страницу и получить её содержимое"""
    if not plasmate_tool:
        return "❌ Plasmate не доступен"
    
    try:
        result = plasmate_tool(url)
        content = str(result)
        
        if len(content) > 3000:
            content = content[:3000] + "..."
        
        return f"✅ Страница загружена:\n{content}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:200]}"

def ask_webpage(url: str, question: str) -> str:
    """Задать вопрос по содержимому страницы (через DSPy)"""
    if not plasmate_tool:
        return "❌ Plasmate не доступен"
    
    try:
        # Получаем содержимое
        result = plasmate_tool(url)
        content = str(result)
        
        # Ограничиваем для LLM
        if len(content) > 8000:
            content = content[:8000] + "..."
        
        # Используем DSPy напрямую
        if AGNES_API_KEY:
            lm = AgnesLM(api_key=AGNES_API_KEY)
            response = lm(f"""
                Ответь на вопрос на основе текста страницы.
                
                Текст страницы:
                {content}
                
                Вопрос: {question}
                
                Ответ должен быть кратким и по существу.
            """)
            return f"📝 Ответ: {response[0] if isinstance(response, list) else response}"
        else:
            return f"📄 Контент страницы:\n{content[:2000]}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:200]}"

def search_web(query: str) -> str:
    """Поискать информацию в интернете"""
    if not plasmate_tool:
        return "❌ Plasmate не доступен"
    
    try:
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        result = plasmate_tool(search_url)
        content = str(result)
        
        # Парсим заголовки
        snippets = re.findall(r'<h3[^>]*>(.*?)</h3>', content, re.IGNORECASE)
        
        if snippets:
            output = f"🔍 Результаты поиска по '{query}':\n"
            for i, snippet in enumerate(snippets[:5], 1):
                clean = re.sub(r'<[^>]+>', '', snippet).strip()
                output += f"{i}. {clean}\n"
            return output
        
        return f"📄 Страница поиска:\n{content[:2000]}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:200]}"

def get_page_title(url: str) -> str:
    """Получить заголовок страницы"""
    if not plasmate_tool:
        return "❌ Plasmate не доступен"
    
    try:
        result = plasmate_tool(url)
        # Пытаемся найти заголовок
        import re
        title_match = re.search(r'<title>(.*?)</title>', str(result), re.IGNORECASE)
        if title_match:
            return f"📌 Заголовок: {title_match.group(1)}"
        return f"📌 Заголовок: {str(result)[:200]}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:200]}"

def extract_links(url: str) -> str:
    """Извлечь ссылки со страницы"""
    if not plasmate_tool:
        return "❌ Plasmate не доступен"
    
    try:
        result = plasmate_tool(url)
        content = str(result)
        
        # Парсим ссылки
        links = re.findall(r'href=[\'"]?([^\'" >]+)', content, re.IGNORECASE)
        unique_links = list(dict.fromkeys(links))[:10]
        
        if unique_links:
            output = "🔗 Ссылки на странице:\n"
            for i, link in enumerate(unique_links, 1):
                output += f"{i}. {link}\n"
            return output
        return "🔗 Ссылок не найдено"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:200]}"

# ==================== СПИСОК ИНСТРУМЕНТОВ ====================
tools = [
    Tool(fetch_page, name="fetch_page", desc="Открыть веб-страницу и получить её текст"),
    Tool(ask_webpage, name="ask_webpage", desc="Задать вопрос по содержимому страницы. Нужны url и вопрос"),
    Tool(search_web, name="search_web", desc="Поискать информацию в интернете по запросу"),
    Tool(get_page_title, name="get_page_title", desc="Получить заголовок страницы по URL"),
    Tool(extract_links, name="extract_links", desc="Извлечь все ссылки со страницы"),
]

# ==================== LM ДЛЯ DSPy ====================
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
    
    def forward(self, prompt=None, messages=None, **kwargs):
        if not self.api_key:
            return ["Ошибка: нет API ключа"]
        
        api_messages = messages or [{"role": "user", "content": prompt or ""}]
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature": 0.3,
            "max_tokens": 2000
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
                if "choices" in data:
                    return [data["choices"][0]["message"]["content"]]
                return ["Ошибка: пустой ответ"]
        except Exception as e:
            return [f"Ошибка: {str(e)}"]
    
    def __call__(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)

# ==================== DSPy АГЕНТ ====================
class BrowserTask(Signature):
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Ответ на задачу")

browser_agent = None

if AGNES_API_KEY and PLASMATE_AVAILABLE:
    try:
        lm = AgnesLM(api_key=AGNES_API_KEY)
        settings.configure(lm=lm)
        
        browser_agent = ReActV2(
            signature=BrowserTask,
            tools=tools,
            max_iters=15,
        )
        logger.info("✅ DSPy агент с Plasmate создан")
    except Exception as e:
        logger.error(f"❌ Ошибка создания агента: {e}")
else:
    logger.warning("⚠️ DSPy агент не создан: проверьте API ключ и Plasmate")

# ==================== ТЕЛЕГРАМ БОТ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "✅ Plasmate готов" if plasmate_tool else "❌ Plasmate не доступен"
    dspy_status = "✅ DSPy активен" if browser_agent else "❌ DSPy отключен"
    
    await update.message.reply_text(
        f"🤖 Бот готов!\n\n"
        f"🌐 {status}\n"
        f"🧠 {dspy_status}\n"
        f"📊 Инструментов: {len(tools)}\n\n"
        f"Используй:\n"
        f"/dspy <запрос> — выполнить задачу\n"
        f"/fetch <url> — открыть страницу\n"
        f"/ask <url> | <вопрос> — спросить по странице\n"
        f"/search <запрос> — поискать в интернете"
    )

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not browser_agent:
        await update.message.reply_text("❌ DSPy не инициализирован")
        return
    
    if not context.args:
        await update.message.reply_text("📝 Напиши задачу после /dspy")
        return
    
    query = " ".join(context.args)
    logger.info(f"🧠 Запрос: {query}")
    
    msg = await update.message.reply_text("⏳ Думаю...")
    
    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            def run_agent():
                return browser_agent(question=query)
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(executor, run_agent)
        
        if hasattr(result, 'answer'):
            answer = result.answer
        elif isinstance(result, list):
            answer = result[0] if result else "Нет ответа"
        else:
            answer = str(result)
        
        if answer and len(answer) > 10:
            await msg.edit_text(f"✅ {answer[:4000]}")
        else:
            await msg.edit_text("❌ Не удалось выполнить задачу")
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def fetch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("📝 Укажи URL после /fetch")
        return
    
    url = context.args[0]
    result = fetch_page(url)
    await update.message.reply_text(result[:4000])

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("📝 Используй: /ask <url> | <вопрос>")
        return
    
    full = " ".join(context.args)
    if "|" not in full:
        await update.message.reply_text("📝 Используй разделитель | между url и вопросом")
        return
    
    url, question = full.split("|", 1)
    url = url.strip()
    question = question.strip()
    
    result = ask_webpage(url, question)
    await update.message.reply_text(result[:4000])

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("📝 Укажи поисковый запрос после /search")
        return
    
    query = " ".join(context.args)
    result = search_web(query)
    await update.message.reply_text(result[:4000])

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    logger.info("🚀 Запуск бота с Plasmate...")
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dspy", dspy_command))
    app.add_handler(CommandHandler("fetch", fetch_command))
    app.add_handler(CommandHandler("ask", ask_command))
    app.add_handler(CommandHandler("search", search_command))
    
    logger.info("✅ Бот запущен!")
    app.run_polling(drop_pending_updates=True)  # Фикс конфликта