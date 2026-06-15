import os
import json
import datetime
import requests
import base64
import time
import logging
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

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

# Проверка обязательных переменных
if not TELEGRAM_BOT_TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN не найден!")
    raise ValueError("TELEGRAM_BOT_TOKEN is required")
if not OPENROUTER_API_KEY:
    logger.error("❌ OPENROUTER_API_KEY не найден!")
    raise ValueError("OPENROUTER_API_KEY is required")

logger.info("✅ Конфигурация загружена успешно")

# ==================== БЕСПЛАТНЫЕ МОДЕЛИ OPENROUTER ====================
FREE_MODELS = [
    "openai/gpt-oss-120b",
    "nvidia/nemotron-3-ultra",
    "nvidia/nemotron-3-super",
    "google/gemma-4-31b-it",
    "google/gemma-4-26b-a4b-it",
    "z-ai/glm-4.5-air",
    "moonshot/kimi-k2.6",
    "poolside/laguna-m.1",
    "poolside/laguna-xs.2",
    "openai/gpt-oss-20b",
    "nvidia/nemotron-3-nano-30b-a3b",
    "nvidia/nemotron-nano-9b-v2",
    "riverflow/riverflow-v2.5-pro",
    "riverflow/riverflow-v2.5-fast",
]

# ==================== УПРАВЛЕНИЕ МОДЕЛЯМИ ====================
class ModelManager:
    def __init__(self):
        self.current_model_index = 0
        self.model_failures = defaultdict(int)
        self.daily_usage = defaultdict(int)
        self.last_reset_date = datetime.datetime.now().date()
        self.REQUESTS_PER_DAY_LIMIT = 50
        
    def _check_reset(self):
        today = datetime.datetime.now().date()
        if today != self.last_reset_date:
            self.daily_usage.clear()
            self.last_reset_date = today
            
    def get_current_model(self) -> str:
        return FREE_MODELS[self.current_model_index % len(FREE_MODELS)]
    
    def get_next_model(self) -> str:
        self.current_model_index += 1
        model = self.get_current_model()
        logger.info(f"🔄 Переключение на модель: {model}")
        return model
    
    def record_failure(self, model: str, error: str):
        self.model_failures[model] += 1
        logger.warning(f"⚠️ Ошибка модели {model}: {error}")
        
    def record_success(self, model: str):
        self.model_failures[model] = 0
        self.daily_usage[model] += 1
        
    def can_use_model(self, model: str) -> bool:
        self._check_reset()
        return self.daily_usage[model] < self.REQUESTS_PER_DAY_LIMIT and self.model_failures[model] < 3
    
    def get_available_models(self) -> list:
        return [m for m in FREE_MODELS if self.can_use_model(m)]

# ==================== РУКИ (ИНСТРУМЕНТЫ) ====================
class Hands:
    
    @staticmethod
    def github_get_repo(owner: str, repo: str) -> str:
        """Получить информацию о репозитории GitHub"""
        if not GITHUB_TOKEN:
            return "❌ GitHub токен не настроен"
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}"
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
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
    def github_list_repos(username: str) -> str:
        """Список репозиториев пользователя"""
        if not GITHUB_TOKEN:
            return "❌ GitHub токен не настроен"
        try:
            url = f"https://api.github.com/users/{username}/repos"
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                repos = response.json()[:10]
                if not repos:
                    return "📭 Репозитории не найдены"
                result = f"📚 **Репозитории {username}:**\n\n"
                for r in repos:
                    result += f"• [{r['name']}]({r['html_url']}) - ⭐ {r['stargazers_count']}\n"
                return result
            return f"❌ Ошибка: {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    @staticmethod
    def render_list_services() -> str:
        """Список сервисов на Render"""
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
                for s in services[:10]:
                    result += f"• **{s.get('name', 'Без имени')}** - {s.get('status', 'unknown')}\n  ID: `{s.get('id')}`\n"
                return result
            return f"❌ Ошибка: {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    @staticmethod
    def render_deploy_service(service_id: str) -> str:
        """Запустить деплой сервиса"""
        if not RENDER_API_KEY:
            return "❌ Render API ключ не настроен"
        try:
            url = f"https://api.render.com/v1/services/{service_id}/deploys"
            headers = {
                "Authorization": f"Bearer {RENDER_API_KEY}",
                "Content-Type": "application/json"
            }
            response = requests.post(url, headers=headers, json={}, timeout=30)
            if response.status_code == 201:
                return f"✅ Деплой запущен! ID: {response.json().get('id')}"
            return f"❌ Ошибка: {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    @staticmethod
    def get_current_time() -> str:
        """Текущее время"""
        now = datetime.datetime.now()
        return f"📅 {now.strftime('%d.%m.%Y')} ⏰ {now.strftime('%H:%M:%S')}"
    
    @staticmethod
    def calculate(expression: str) -> str:
        """Вычислить выражение"""
        try:
            allowed = set("0123456789+-*/(). ")
            if not all(c in allowed for c in expression):
                return "❌ Разрешены только цифры и операторы"
            result = eval(expression)
            return f"📐 Результат: {result}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    @staticmethod
    def execute_code(code: str) -> str:
        """Выполнить Python код"""
        try:
            exec_globals = {"__builtins__": {"print": print, "len": len, "str": str}}
            exec(code, exec_globals)
            return "✅ Код выполнен"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    @staticmethod
    def show_models() -> str:
        """Показать доступные модели"""
        models_list = "\n".join([f"• {i+1}. {m}" for i, m in enumerate(FREE_MODELS)])
        return f"🤖 **Доступные модели:**\n\n{models_list}"
    
    TOOLS_SCHEMA = [
        {"type": "function", "function": {"name": "github_get_repo", "description": "Информация о репозитории GitHub", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["owner", "repo"]}}},
        {"type": "function", "function": {"name": "github_list_repos", "description": "Список репозиториев пользователя", "parameters": {"type": "object", "properties": {"username": {"type": "string"}}, "required": ["username"]}}},
        {"type": "function", "function": {"name": "render_list_services", "description": "Список сервисов на Render", "parameters": {"type": "object", "properties": {}, "required": []}}},
        {"type": "function", "function": {"name": "render_deploy_service", "description": "Запустить деплой на Render", "parameters": {"type": "object", "properties": {"service_id": {"type": "string"}}, "required": ["service_id"]}}},
        {"type": "function", "function": {"name": "get_current_time", "description": "Текущее время", "parameters": {"type": "object", "properties": {}, "required": []}}},
        {"type": "function", "function": {"name": "calculate", "description": "Вычислить выражение", "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}}},
        {"type": "function", "function": {"name": "execute_code", "description": "Выполнить Python код", "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}}},
        {"type": "function", "function": {"name": "show_models", "description": "Список доступных моделей AI", "parameters": {"type": "object", "properties": {}, "required": []}}}
    ]

# ==================== МОЗГ (OPENROUTER) ====================
class Brain:
    def __init__(self):
        self.conversation_history = []
        self.model_manager = ModelManager()
    
    def _make_request(self, model: str, tools: list = None) -> dict:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": self.conversation_history,
            "temperature": 0.7,
            "max_tokens": 1000
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=60
            )
            if response.status_code in [429, 402]:
                return {"error": "Rate limit exceeded", "rate_limited": True}
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e), "rate_limited": False}
    
    def think(self, user_message: str, tools: list = None) -> dict:
        self.conversation_history.append({"role": "user", "content": user_message})
        
        available_models = self.model_manager.get_available_models()
        if not available_models:
            available_models = FREE_MODELS
        
        for model in available_models:
            if not self.model_manager.can_use_model(model):
                continue
            
            logger.info(f"🧠 Используем модель: {model}")
            response = self._make_request(model, tools)
            
            if "error" not in response:
                self.model_manager.record_success(model)
                if "choices" in response:
                    self.conversation_history.append(response["choices"][0]["message"])
                response["_model_used"] = model
                return response
            
            self.model_manager.record_failure(model, response.get("error", ""))
            self.model_manager.get_next_model()
        
        return {
            "error": "Все модели временно недоступны",
            "choices": [{"message": {"content": "😔 Извините, все AI-модели сейчас недоступны. Попробуйте позже."}}]
        }
    
    def clear(self):
        self.conversation_history = []

# ==================== ТЕЛЕГРАМ БОТ ====================
class TelegramBot:
    def __init__(self):
        self.brain = Brain()
        self.hands = Hands()
        self.app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("clear", self.cmd_clear))
        self.app.add_handler(CommandHandler("models", self.cmd_models))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    async def cmd_start(self, update: Update, context: CallbackContext):
        await update.message.reply_text("""
🧠 **AI Бот с переключением моделей**

**Возможности:**
• 📦 GitHub API (репозитории)
• 🖥️ Render API (деплой)
• 📐 Математика
• 🐍 Выполнение кода

**Команды:**
• /models - список AI моделей
• /status - статус и лимиты
• /clear - очистить историю

Просто задайте вопрос или дайте команду!
""", parse_mode="Markdown")
    
    async def cmd_clear(self, update: Update, context: CallbackContext):
        self.brain.clear()
        await update.message.reply_text("🧹 История очищена!")
    
    async def cmd_models(self, update: Update, context: CallbackContext):
        result = self.hands.show_models()
        await update.message.reply_text(result, parse_mode="Markdown")
    
    async def cmd_status(self, update: Update, context: CallbackContext):
        current = self.brain.model_manager.get_current_model()
        available = len(self.brain.model_manager.get_available_models())
        status = f"""
📊 **Статус**
• Текущая модель: `{current}`
• Доступно моделей: {available}/{len(FREE_MODELS)}
• Лимит: {self.brain.model_manager.REQUESTS_PER_DAY_LIMIT}/день на модель
"""
        await update.message.reply_text(status, parse_mode="Markdown")
    
    async def handle_message(self, update: Update, context: CallbackContext):
        user_text = update.message.text
        await update.message.chat.send_action(action="typing")
        
        response = self.brain.think(user_text, Hands.TOOLS_SCHEMA)
        
        if "error" in response and "choices" not in response:
            await update.message.reply_text(f"❌ {response['error']}")
            return
        
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
            await update.message.reply_text(f"🔥 Ошибка: {e}")
    
    def run(self):
        logger.info("🚀 Бот запущен!")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    bot = TelegramBot()
    bot.run()
