import os
import logging
import httpx
import re
import subprocess
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

# ==================== ИНСТРУМЕНТЫ (через subprocess) ====================

def run_plasmate(url: str, format_type: str = "text") -> str:
    """Выполняет plasmate fetch с нужным форматом"""
    try:
        result = subprocess.run(
            ["plasmate", "fetch", url, "--format", format_type],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return result.stdout
        else:
            return f"❌ Ошибка: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return "❌ Таймаут (30 сек)"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:200]}"

def fetch_page(url: str) -> str:
    """Открыть страницу и получить её текст"""
    try:
        content = run_plasmate(url, "text")
        
        if content.startswith("❌"):
            return content
        
        if len(content) > 3000:
            content = content[:3000] + "..."
        
        return f"✅ Страница загружена:\n{content}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:200]}"

def ask_webpage(url: str, question: str) -> str:
    """Задать вопрос по содержимому страницы"""
    try:
        content = run_plasmate(url, "text")
        
        if content.startswith("❌"):
            return content
        
        if len(content) > 8000:
            content = content[:8000] + "..."
        
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
    try:
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        content = run_plasmate(search_url, "text")
        
        if content.startswith("❌"):
            return content
        
        # Парсим заголовки (упрощённо)
        lines = content.split('\n')
        results = []
        for line in lines:
            if len(line.strip()) > 10:
                results.append(line.strip())
        
        if results:
            output = f"🔍 Результаты поиска по '{query}':\n"
            for i, line in enumerate(results[:5], 1):
                output += f"{i}. {line[:150]}\n"
            return output
        
        return f"📄 Страница поиска:\n{content[:2000]}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:200]}"

def get_page_title(url: str) -> str:
    """Получить заголовок страницы"""
    try:
        content = run_plasmate(url, "text")
        
        if content.startswith("❌"):
            return content
        
        # Ищем первую строку как заголовок
        lines = content.split('\n')
        for line in lines:
            if line.strip():
                return f"📌 Заголовок: {line.strip()[:200]}"
        
        return "📌 Заголовок не найден"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:200]}"

def extract_links(url: str) -> str:
    """Извлечь ссылки со страницы (через SOM)"""
    try:
        # Используем JSON формат для структурированных данных
        content = run_plasmate(url, "json")
        
        if content.startswith("❌"):
            return content
        
        # Парсим JSON
        import json
        try:
            data = json.loads(content)
            links = []
            
            # Ищем ссылки в JSON
            if isinstance(data, dict):
                # Рекурсивный поиск URL
                import re
                text = json.dumps(data)
                found = re.findall(r'https?://[^\s"\'<>]+', text)
                unique = list(dict.fromkeys(found))[:10]
                
                if unique:
                    output = "🔗 Ссылки на странице:\n"
                    for i, link in enumerate(unique, 1):
                        output += f"{i}. {link}\n"
                    return output
        except:
            pass
        
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

if AGNES_API_KEY:
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
    logger.warning("⚠️ DSPy агент не создан: нет API ключа")

# ==================== ТЕЛЕГРАМ БОТ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем Plasmate
    try:
        test = subprocess.run(["plasmate", "--version"], capture_output=True, text=True, timeout=5)
        plasm_status = f"✅ Plasmate {test.stdout.strip()}" if test.returncode == 0 else "❌ Plasmate не найден"
    except:
        plasm_status = "❌ Plasmate не доступен"
    
    dspy_status = "✅ DSPy активен" if browser_agent else "❌ DSPy отключен"
    
    await update.message.reply_text(
        f"🤖 Бот готов!\n\n"
        f"🌐 {plasm_status}\n"
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
    app.run_polling(drop_pending_updates=True)