import os
import json
import datetime
import requests
import logging
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== КОНФИГУРАЦИЯ ИЗ ОКРУЖЕНИЯ ====================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
RENDER_API_KEY = os.environ.get("RENDER_API_KEY", "")

if not TELEGRAM_BOT_TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN не найден!")
    raise ValueError("TELEGRAM_BOT_TOKEN is required")

if not OPENROUTER_API_KEY:
    logger.warning("⚠️ OPENROUTER_API_KEY не найден! Бот будет работать ограниченно")

logger.info("✅ Конфигурация загружена")

# ==================== БЕСПЛАТНЫЕ МОДЕЛИ ====================
FREE_MODELS = [
    "openai/gpt-oss-120b",
    "nvidia/nemotron-3-ultra",
    "google/gemma-4-31b-it",
    "moonshot/kimi-k2.6",
    "openai/gpt-oss-20b",
]

# ==================== УПРАВЛЕНИЕ МОДЕЛЯМИ ====================
class ModelManager:
    def __init__(self):
        self.current_index = 0
        self.failures = defaultdict(int)
        self.daily_usage = defaultdict(int)
        self.last_reset = datetime.datetime.now().date()
        self.DAILY_LIMIT = 50
    
    def _reset_if_needed(self):
        today = datetime.datetime.now().date()
        if today != self.last_reset:
            self.daily_usage.clear()
            self.last_reset = today
    
    def get_current(self) -> str:
        return FREE_MODELS[self.current_index % len(FREE_MODELS)]
    
    def next_model(self) -> str:
        self.current_index += 1
        model = self.get_current()
        logger.info(f"🔄 Переключение на модель: {model}")
        return model
    
    def record_failure(self, model: str, error: str):
        self.failures[model] += 1
        logger.warning(f"⚠️ Ошибка {model}: {error}")
    
    def record_success(self, model: str):
        self.failures[model] = 0
        self.daily_usage[model] += 1
    
    def can_use(self, model: str) -> bool:
        self._reset_if_needed()
        return self.daily_usage[model] < self.DAILY_LIMIT and self.failures[model] < 3

# ==================== ИНСТРУМЕНТЫ ====================
class Hands:
    
    @staticmethod
    def get_current_time() -> str:
        now = datetime.datetime.now()
        return f"📅 {now.strftime('%d.%m.%Y')} ⏰ {now.strftime('%H:%M:%S')}"
    
    @staticmethod
    def calculate(expression: str) -> str:
        try:
            allowed = set("0123456789+-*/(). ")
            if not all(c in allowed for c in expression):
                return "❌ Только цифры и операторы"
            result = eval(expression)
            return f"📐 Результат: {result}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    @staticmethod
    def github_get_repo(owner: str, repo: str) -> str:
        if not GITHUB_TOKEN:
            return "❌ GitHub токен не настроен"
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}"
            headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return f"""
📦 **{data['full_name']}**
⭐ Звёзд: {data['stargazers_count']}
🍴 Форков: {data['forks_count']}
📝 {data.get('description', 'Нет описания')}
🔗 {data['html_url']}
"""
            return f"❌ Ошибка: {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    @staticmethod
    def render_list_services() -> str:
        if not RENDER_API_KEY:
            return "❌ Render API ключ не настроен"
        try:
            url = "https://api.render.com/v1/services"
            headers = {"Authorization": f"Bearer {RENDER_API_KEY}"}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                services = response.json()
                if not services:
                    return "📭 Сервисы не найдены"
                result = "🖥️ **Сервисы на Render:**\n\n"
                for s in services[:5]:
                    result += f"• **{s.get('name', 'Без имени')}** - {s.get('status', 'unknown')}\n"
                return result
            return f"❌ Ошибка: {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    @staticmethod
    def show_models() -> str:
        models = "\n".join([f"• {m}" for m in FREE_MODELS])
        return f"🤖 **Доступные модели:**\n\n{models}"
    
    TOOLS = [
        {"type": "function", "function": {"name": "get_current_time", "description": "Текущее время", "parameters": {"type": "object", "properties": {}, "required": []}}},
        {"type": "function", "function": {"name": "calculate", "description": "Вычислить выражение", "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}}},
        {"type": "function", "function": {"name": "github_get_repo", "description": "Информация о репозитории", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["owner", "repo"]}}},
        {"type": "function", "function": {"name": "render_list_services", "description": "Список сервисов Render", "parameters": {"type": "object", "properties": {}, "required": []}}},
        {"type": "function", "function": {"name": "show_models", "description": "Список AI моделей", "parameters": {"type": "object", "properties": {}, "required": []}}}
    ]

# ==================== МОЗГ ====================
class Brain:
    def __init__(self):
        self.history = []
        self.manager = ModelManager()
    
    def _call_api(self, model: str, tools=None):
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": self.history,
            "temperature": 0.7,
            "max_tokens": 500
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=30
            )
            if response.status_code in [429, 402]:
                return {"error": "Лимит", "rate_limited": True}
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e), "rate_limited": False}
    
    def think(self, message: str, tools=None):
        self.history.append({"role": "user", "content": message})
        
        for model in FREE_MODELS:
            if not self.manager.can_use(model):
                continue
            
            logger.info(f"🧠 Модель: {model}")
            resp = self._call_api(model, tools)
            
            if "error" not in resp:
                self.manager.record_success(model)
                if "choices" in resp:
                    self.history.append(resp["choices"][0]["message"])
                return resp
            self.manager.record_failure(model, resp["error"])
            self.manager.next_model()
        
        return {"choices": [{"message": {"content": "😔 Все модели временно недоступны"}}]}
    
    def clear(self):
        self.history = []

# ==================== ТЕЛЕГРАМ БОТ ====================
class Bot:
    def __init__(self):
        self.brain = Brain()
        self.hands = Hands()
        self.app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self._setup_handlers()
    
    def _setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("clear", self.clear))
        self.app.add_handler(CommandHandler("models", self.models))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle))
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 **Бот готов!**\n\n"
            "Команды:\n"
            "/models - список AI моделей\n"
            "/clear - очистить историю\n\n"
            "Просто задайте вопрос!",
            parse_mode="Markdown"
        )
    
    async def clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.brain.clear()
        await update.message.reply_text("🧹 История очищена!")
    
    async def models(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        result = self.hands.show_models()
        await update.message.reply_text(result, parse_mode="Markdown")
    
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_msg = update.message.text
        await update.message.chat.send_action(action="typing")
        
        response = self.brain.think(user_msg, Hands.TOOLS)
        
        try:
            message = response["choices"][0]["message"]
            
            if "tool_calls" in message:
                for tool in message["tool_calls"]:
                    name = tool["function"]["name"]
                    args = json.loads(tool["function"]["arguments"])
                    if hasattr(self.hands, name):
                        result = getattr(self.hands, name)(**args)
                        await update.message.reply_text(result, parse_mode="Markdown")
            else:
                reply = message.get("content", "🤔 Не знаю...")
                await update.message.reply_text(reply, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    def run(self):
        logger.info("🚀 Бот запущен!")
        self.app.run_polling()

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    bot = Bot()
    bot.run()
