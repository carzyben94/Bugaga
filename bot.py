import json
import subprocess
import datetime
import requests
import os
import base64
import random
import time
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

# ==================== КОНФИГУРАЦИЯ ====================
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"
OPENROUTER_API_KEY = "sk-or-v1-YOUR_OPENROUTER_KEY_HERE"  # Основной ключ

# API ключи для сервисов
GITHUB_TOKEN = "github_pat_YOUR_GITHUB_TOKEN_HERE"
RENDER_API_KEY = "rnd_your_render_api_key_here"

# ==================== БЕСПЛАТНЫЕ МОДЕЛИ OPENROUTER ====================
# Полный список бесплатных моделей с приоритетом (от лучших к базовым) [citation:1]
FREE_MODELS = [
    "openai/gpt-oss-120b",           # OpenAI 120B MoE - отличная для agentic задач
    "nvidia/nemotron-3-ultra",       # NVIDIA 550B MoE, 1M контекст
    "nvidia/nemotron-3-super",       # NVIDIA 120B MoE, 1M контекст
    "google/gemma-4-31b-it",         # Google Gemma 4 31B, 256K контекст
    "google/gemma-4-26b-a4b-it",     # Google Gemma 4 MoE, 256K контекст
    "z-ai/glm-4.5-air",              # GLM 4.5 Air, для agent-приложений
    "moonshot/kimi-k2.6",            # Kimi K2.6, кодинг и мультиагент
    "poolside/laguna-m.1",           # Poolside - кодинг агент
    "poolside/laguna-xs.2",          # Poolside XS - легковесный кодинг
    "openai/gpt-oss-20b",            # OpenAI 20B MoE, легковесный
    "nvidia/nemotron-3-nano-30b-a3b", # NVIDIA Nano 30B MoE
    "nvidia/nemotron-nano-9b-v2",     # NVIDIA Nano 9B
    "riverflow/riverflow-v2.5-pro",   # Riverflow Pro
    "riverflow/riverflow-v2.5-fast",  # Riverflow Fast
]

# Модели для специфических задач (распознавание, генерация изображений)
VISION_MODELS = [
    "google/gemma-4-31b-it",          # Мультимодальная
    "nvidia/nemotron-3-nano-omni",    # Видео + аудио
]

IMAGE_MODELS = [
    "bytedance-seed/seedream-4.5",    # Генерация изображений (платная: $0.04/изображение)
]

# ==================== УПРАВЛЕНИЕ ЛИМИТАМИ И ПЕРЕКЛЮЧЕНИЕМ ====================
class ModelManager:
    """Управляет моделями, лимитами и автоматическим переключением"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.current_model_index = 0
        self.model_failures = defaultdict(int)  # Счётчик ошибок на модель
        self.model_last_used = defaultdict(float)  # Время последнего использования
        self.daily_usage = defaultdict(int)  # Использование за день
        self.last_reset_date = datetime.datetime.now().date()
        
        # Лимиты OpenRouter для бесплатных моделей [citation:3]
        self.REQUESTS_PER_MINUTE = 20
        self.REQUESTS_PER_DAY_LIMIT = 50  # Базовый лимит (<10 credits)
        
    def _check_and_reset_daily(self):
        """Сброс дневного счётчика"""
        today = datetime.datetime.now().date()
        if today != self.last_reset_date:
            self.daily_usage.clear()
            self.last_reset_date = today
            
    def get_current_model(self) -> str:
        """Получить текущую модель"""
        return FREE_MODELS[self.current_model_index % len(FREE_MODELS)]
    
    def get_next_model(self) -> str:
        """Переключиться на следующую модель"""
        self.current_model_index += 1
        model = self.get_current_model()
        print(f"🔄 Переключение на модель: {model}")
        return model
    
    def record_failure(self, model: str, error: str):
        """Записать ошибку для модели"""
        self.model_failures[model] += 1
        print(f"⚠️ Ошибка модели {model}: {error}")
        
        # Если модель много раз ошибается, переключаемся
        if self.model_failures[model] >= 3:
            print(f"❌ Модель {model} временно заблокирована из-за ошибок")
            
    def record_success(self, model: str):
        """Записать успешный запрос"""
        self.model_failures[model] = 0
        self.model_last_used[model] = time.time()
        self.daily_usage[model] += 1
        
    def can_use_model(self, model: str) -> bool:
        """Проверить, можно ли использовать модель"""
        self._check_and_reset_daily()
        
        # Проверка дневного лимита
        if self.daily_usage[model] >= self.REQUESTS_PER_DAY_LIMIT:
            return False
            
        return True
    
    def get_best_available_model(self) -> str:
        """Найти лучшую доступную модель"""
        for i in range(len(FREE_MODELS)):
            model = FREE_MODELS[(self.current_model_index + i) % len(FREE_MODELS)]
            if self.can_use_model(model) and self.model_failures[model] < 3:
                self.current_model_index = (self.current_model_index + i) % len(FREE_MODELS)
                return model
        return FREE_MODELS[0]  # fallback
    
    def get_models_for_fallback(self) -> list:
        """Получить список моделей для fallback (сначала лучшие, потом запасные)"""
        available = [m for m in FREE_MODELS if self.can_use_model(m) and self.model_failures[m] < 3]
        if not available:
            available = FREE_MODELS.copy()
        return available


# ==================== РУКИ (АГЕНТ ИСПОЛНИТЕЛЬ) ====================
class Hands:
    """Класс-исполнитель. Содержит все действия, которые может делать бот"""
    
    # GitHub API методы
    @staticmethod
    def github_get_repo(owner: str, repo: str) -> str:
        """Получить информацию о репозитории GitHub"""
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}"
            headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN != "github_pat_YOUR_GITHUB_TOKEN_HERE" else {}
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                info = f"""
📦 **Репозиторий:** {data['full_name']}
⭐ **Звёзд:** {data['stargazers_count']}
🍴 **Форков:** {data['forks_count']}
📝 **Описание:** {data.get('description', 'Нет описания')}
🔗 **Ссылка:** {data['html_url']}
                """
                return info.strip()
            else:
                return f"❌ Ошибка GitHub API: {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    @staticmethod
    def github_create_issue(owner: str, repo: str, title: str, body: str = "") -> str:
        """Создать Issue в GitHub репозитории"""
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/issues"
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }
            data = {"title": title, "body": body}
            response = requests.post(url, json=data, headers=headers)
            
            if response.status_code == 201:
                issue_url = response.json()["html_url"]
                return f"✅ Issue создан! Ссылка: {issue_url}"
            else:
                return f"❌ Ошибка создания Issue: {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    @staticmethod
    def github_list_repos(username: str) -> str:
        """Получить список репозиториев пользователя GitHub"""
        try:
            url = f"https://api.github.com/users/{username}/repos"
            headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN != "github_pat_YOUR_GITHUB_TOKEN_HERE" else {}
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                repos = response.json()
                if not repos:
                    return "📭 Репозитории не найдены"
                
                repo_list = "\n".join([f"• [{repo['name']}]({repo['html_url']}) - ⭐ {repo['stargazers_count']}" for repo in repos[:10]])
                return f"📚 **Репозитории {username}:**\n\n{repo_list}"
            else:
                return f"❌ Ошибка: {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    @staticmethod
    def github_get_readme(owner: str, repo: str) -> str:
        """Получить README файл из репозитория"""
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/readme"
            headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN != "github_pat_YOUR_GITHUB_TOKEN_HERE" else {}
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                content = base64.b64decode(data['content']).decode('utf-8')
                return f"📖 **README из {owner}/{repo}:**\n\n{content[:1000]}{'...' if len(content) > 1000 else ''}"
            else:
                return f"❌ README не найден"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    # Render API методы
    @staticmethod
    def render_list_services() -> str:
        """Получить список всех сервисов на Render"""
        try:
            if RENDER_API_KEY == "rnd_your_render_api_key_here":
                return "❌ Render API ключ не настроен"
            
            url = "https://api.render.com/v1/services"
            headers = {"Authorization": f"Bearer {RENDER_API_KEY}"}
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                services = response.json()
                if not services:
                    return "📭 Сервисы не найдены"
                
                service_list = []
                for service in services:
                    name = service.get('name', 'Без имени')
                    status = service.get('status', 'unknown')
                    service_type = service.get('type', 'unknown')
                    service_list.append(f"• **{name}** ({service_type}) - статус: {status}")
                
                return "🖥️ **Сервисы на Render:**\n\n" + "\n".join(service_list)
            else:
                return f"❌ Ошибка Render API: {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    @staticmethod
    def render_get_service(service_id: str) -> str:
        """Получить детальную информацию о сервисе Render"""
        try:
            if RENDER_API_KEY == "rnd_your_render_api_key_here":
                return "❌ Render API ключ не настроен"
            
            url = f"https://api.render.com/v1/services/{service_id}"
            headers = {"Authorization": f"Bearer {RENDER_API_KEY}"}
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                service = response.json()
                info = f"""
🖥️ **Сервис:** {service.get('name', 'N/A')}
📊 **Статус:** {service.get('status', 'N/A')}
🔧 **Тип:** {service.get('type', 'N/A')}
🌐 **URL:** {service.get('serviceDetails', {}).get('url', 'N/A')}
📅 **Создан:** {service.get('createdAt', 'N/A')}
                """
                return info.strip()
            else:
                return f"❌ Ошибка: {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    @staticmethod
    def render_deploy_service(service_id: str) -> str:
        """Запустить деплой сервиса на Render"""
        try:
            if RENDER_API_KEY == "rnd_your_render_api_key_here":
                return "❌ Render API ключ не настроен"
            
            url = f"https://api.render.com/v1/services/{service_id}/deploys"
            headers = {
                "Authorization": f"Bearer {RENDER_API_KEY}",
                "Content-Type": "application/json"
            }
            response = requests.post(url, headers=headers, json={})
            
            if response.status_code == 201:
                return f"✅ Деплой запущен успешно! ID: {response.json().get('id')}"
            else:
                return f"❌ Ошибка запуска деплоя: {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    @staticmethod
    def render_get_deploys(service_id: str) -> str:
        """Получить историю деплоев сервиса"""
        try:
            if RENDER_API_KEY == "rnd_your_render_api_key_here":
                return "❌ Render API ключ не настроен"
            
            url = f"https://api.render.com/v1/services/{service_id}/deploys"
            headers = {"Authorization": f"Bearer {RENDER_API_KEY}"}
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                deploys = response.json()[:5]
                if not deploys:
                    return "📭 История деплоев пуста"
                
                deploy_list = []
                for deploy in deploys:
                    status = deploy.get('status', 'unknown')
                    commit = deploy.get('commit', {}).get('message', 'Без сообщения')[:50]
                    created = deploy.get('createdAt', 'N/A')
                    deploy_list.append(f"• {status} - {created}\n  {commit}")
                
                return "📦 **Последние деплои:**\n\n" + "\n\n".join(deploy_list)
            else:
                return f"❌ Ошибка: {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    # Базовые методы
    @staticmethod
    def execute_code(code: str) -> str:
        """Выполнить Python-код"""
        try:
            exec_globals = {"__builtins__": {"print": print, "len": len, "str": str, "int": int, "float": float, "range": range, "list": list, "dict": dict}}
            exec(code, exec_globals)
            return "✅ Код выполнен успешно"
        except Exception as e:
            return f"❌ Ошибка выполнения кода: {e}"
    
    @staticmethod
    def get_current_time() -> str:
        """Получить текущее время и дату"""
        now = datetime.datetime.now()
        return f"📅 {now.strftime('%d.%m.%Y')} ⏰ {now.strftime('%H:%M:%S')}"
    
    @staticmethod
    def calculate(expression: str) -> str:
        """Вычислить математическое выражение"""
        try:
            allowed_chars = set("0123456789+-*/(). ")
            if not all(c in allowed_chars for c in expression):
                return "❌ Разрешены только цифры и операторы + - * / ( )"
            result = eval(expression)
            return f"📐 Результат: {result}"
        except Exception as e:
            return f"❌ Ошибка вычисления: {e}"
    
    @staticmethod
    def get_system_info() -> str:
        """Получить информацию о системе"""
        try:
            import platform
            info = f"""
🖥️ **Системная информация**
• ОС: {platform.system()} {platform.release()}
• Python: {platform.python_version()}
• Время работы: {datetime.datetime.now().strftime('%H:%M:%S')}
            """
            return info.strip()
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    @staticmethod
    def show_available_models() -> str:
        """Показать список доступных бесплатных моделей"""
        models_list = "\n".join([f"• {i+1}. {model}" for i, model in enumerate(FREE_MODELS[:15])])
        return f"🤖 **Доступные бесплатные модели:**\n\n{models_list}\n\n💡 Мозг автоматически переключается при ошибках или лимитах"
    
    # Схема инструментов для Мозга (сокращённая версия для читаемости)
    TOOLS_SCHEMA = [
        {
            "type": "function",
            "function": {
                "name": "github_get_repo",
                "description": "Получить информацию о репозитории GitHub",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"}
                    },
                    "required": ["owner", "repo"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "github_create_issue",
                "description": "Создать Issue в GitHub",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "title": {"type": "string"},
                        "body": {"type": "string"}
                    },
                    "required": ["owner", "repo", "title"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "github_list_repos",
                "description": "Список репозиториев пользователя",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "username": {"type": "string"}
                    },
                    "required": ["username"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "github_get_readme",
                "description": "Прочитать README репозитория",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"}
                    },
                    "required": ["owner", "repo"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "render_list_services",
                "description": "Список сервисов на Render",
                "parameters": {"type": "object", "properties": {}, "required": []}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "render_get_service",
                "description": "Информация о сервисе Render",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_id": {"type": "string"}
                    },
                    "required": ["service_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "render_deploy_service",
                "description": "Запустить деплой на Render",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_id": {"type": "string"}
                    },
                    "required": ["service_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "render_get_deploys",
                "description": "История деплоев на Render",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_id": {"type": "string"}
                    },
                    "required": ["service_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "show_available_models",
                "description": "Показать список доступных бесплатных моделей",
                "parameters": {"type": "object", "properties": {}, "required": []}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "description": "Получить текущее время",
                "parameters": {"type": "object", "properties": {}, "required": []}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "calculate",
                "description": "Вычислить выражение",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string"}
                    },
                    "required": ["expression"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "execute_code",
                "description": "Выполнить Python код",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"}
                    },
                    "required": ["code"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_system_info",
                "description": "Информация о системе",
                "parameters": {"type": "object", "properties": {}, "required": []}
            }
        }
    ]


# ==================== МОЗГ (OPENROUTER С ПОДДЕРЖКОЙ FALLBACK) ====================
class Brain:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.url = "https://openrouter.ai/api/v1/chat/completions"
        self.conversation_history = []
        self.model_manager = ModelManager(api_key)
        self.retry_count = 0
        self.max_retries = len(FREE_MODELS)  # Максимум попыток переключения
        
    def _make_request(self, model: str, tools: list = None) -> dict:
        """Выполнить запрос к конкретной модели"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://telegram-bot.local",
            "X-Title": "Telegram Bot with Smart Model Switching"
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
            response = requests.post(self.url, json=payload, headers=headers, timeout=60)
            
            # Обработка ошибок лимитов [citation:3]
            if response.status_code == 429:
                error_data = response.json()
                error_msg = error_data.get('error', {}).get('message', 'Rate limit exceeded')
                return {"error": error_msg, "rate_limited": True}
            
            if response.status_code == 402:
                return {"error": "Daily limit exceeded for free models", "rate_limited": True}
            
            response.raise_for_status()
            result = response.json()
            
            # Проверка на ошибки в ответе
            if "error" in result:
                return {"error": result["error"].get("message", "Unknown error"), "rate_limited": "rate" in str(result["error"]).lower()}
            
            return result
            
        except requests.exceptions.RequestException as e:
            return {"error": str(e), "rate_limited": False}
    
    def think(self, user_message: str, tools: list = None) -> dict:
        """Отправить запрос в OpenRouter с автоматическим переключением моделей"""
        self.conversation_history.append({"role": "user", "content": user_message})
        
        # Получаем список доступных моделей для fallback [citation:2][citation:9]
        available_models = self.model_manager.get_models_for_fallback()
        
        last_error = None
        
        for model in available_models:
            print(f"🧠 Попытка использования модели: {model}")
            
            # Проверка дневного лимита
            if not self.model_manager.can_use_model(model):
                print(f"⚠️ Модель {model} превысила дневной лимит")
                continue
            
            response = self._make_request(model, tools)
            
            # Успешный ответ
            if "error" not in response:
                self.model_manager.record_success(model)
                self.retry_count = 0
                
                # Сохраняем ответ ассистента в историю
                if "choices" in response:
                    assistant_message = response["choices"][0]["message"]
                    self.conversation_history.append(assistant_message)
                
                # Добавляем информацию об использованной модели в ответ
                response["_model_used"] = model
                return response
            
            # Обработка ошибки
            error_msg = response.get("error", "Unknown error")
            is_rate_limited = response.get("rate_limited", False)
            
            self.model_manager.record_failure(model, error_msg)
            last_error = error_msg
            
            if is_rate_limited:
                print(f"⚠️ Лимит модели {model}: {error_msg}")
                # Помечаем модель как временно недоступную
                self.model_manager.model_failures[model] = 5
            else:
                print(f"❌ Ошибка модели {model}: {error_msg}")
            
            # Переключаемся на следующую модель
            self.model_manager.get_next_model()
        
        # Если все модели не сработали
        return {
            "error": f"Все доступные модели недоступны. Последняя ошибка: {last_error}",
            "choices": [{"message": {"content": f"😔 Извините, все AI-модели временно недоступны. Попробуйте позже или добавьте credits на OpenRouter.\n\nОшибка: {last_error}"}}]
        }
    
    def clear_history(self):
        """Очистить историю диалога"""
        self.conversation_history = []


# ==================== ТЕЛЕГРАМ БОТ ====================
class TelegramBot:
    def __init__(self, telegram_token: str, openrouter_key: str):
        self.brain = Brain(openrouter_key)
        self.hands = Hands()
        self.application = Application.builder().token(telegram_token).build()
        
        # Регистрация обработчиков
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("clear", self.clear_command))
        self.application.add_handler(CommandHandler("models", self.models_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    async def start_command(self, update: Update, context: CallbackContext):
        welcome_text = """
🧠 **Бот с интеллектуальным переключением моделей**

**Архитектура:**
• 🧠 Мозг — OpenRouter с 15+ бесплатными моделями
• 🦾 Руки — GitHub + Render API

**⚡ Умное переключение:**
• Автоматическая смена модели при лимитах
• Обработка 429 (rate limit) и 402 (daily limit)
• Приоритет лучших моделей (GPT-oss, Nemotron, Gemma)
• Fallback на запасные модели

**📌 Команды:**
• /models — список доступных моделей
• /status — статус текущей модели и лимитов
• /clear — очистить историю

**Примеры запросов:**
• «Покажи репозиторий openai/gpt-3»
• «Создай Issue с заголовком Bug»
• «Список моих сервисов на Render»
        """
        await update.message.reply_text(welcome_text, parse_mode="Markdown")
    
    async def clear_command(self, update: Update, context: CallbackContext):
        self.brain.clear_history()
        await update.message.reply_text("🧹 История диалога очищена!")
    
    async def models_command(self, update: Update, context: CallbackContext):
        """Показать доступные модели"""
        models_list = "\n".join([f"• {i+1}. {m}" for i, m in enumerate(FREE_MODELS)])
        current = self.brain.model_manager.get_current_model()
        text = f"🤖 **Доступные бесплатные модели:**\n\n{models_list}\n\n📌 **Текущая модель:** {current}\n\n💡 При лимитах бот автоматически переключается на следующую модель"
        await update.message.reply_text(text, parse_mode="Markdown")
    
    async def status_command(self, update: Update, context: CallbackContext):
        """Показать статус и лимиты"""
        manager = self.brain.model_manager
        current = manager.get_current_model()
        
        status_text = f"""
📊 **Статус моделей**

**Текущая модель:** {current}

**Лимиты OpenRouter:** [citation:3]
• 🔄 Запросов в минуту: {manager.REQUESTS_PER_MINUTE}
• 📅 Запросов в день (free): {manager.REQUESTS_PER_DAY_LIMIT}
• 💡 Совет: добавьте 10+ credits для увеличения до 1000/день

**Статус переключения:**
• Доступно моделей: {len([m for m in FREE_MODELS if manager.can_use_model(m)])}/{len(FREE_MODELS)}
• Всего попыток: {manager.retry_count if hasattr(manager, 'retry_count') else 0}
        """
        await update.message.reply_text(status_text, parse_mode="Markdown")
    
    async def handle_message(self, update: Update, context: CallbackContext):
        """Обработка сообщений с интеллектуальным переключением"""
        user_message = update.message.text
        await update.message.chat.send_action(action="typing")
        
        # Мозг выбирает модель и обрабатывает запрос
        response = self.brain.think(user_message, Hands.TOOLS_SCHEMA)
        
        # Проверка на глобальную ошибку
        if "error" in response and "choices" not in response:
            await update.message.reply_text(f"❌ {response['error']}")
            return
        
        try:
            choice = response["choices"][0]
            message = choice["message"]
            
            # Информация об использованной модели
            model_used = response.get("_model_used", "unknown")
            
            # Если Мозг вызвал инструменты → передаём Рукам
            if "tool_calls" in message and message["tool_calls"]:
                for tool_call in message["tool_calls"]:
                    tool_name = tool_call["function"]["name"]
                    arguments = json.loads(tool_call["function"]["arguments"])
                    
                    if hasattr(self.hands, tool_name):
                        result = getattr(self.hands, tool_name)(**arguments)
                        await update.message.reply_text(result, parse_mode="Markdown")
                    else:
                        await update.message.reply_text(f"❌ Инструмент '{tool_name}' не найден")
            else:
                # Простой текстовый ответ
                reply_text = message.get("content", "🤔 Не знаю, что ответить...")
                if len(reply_text) > 4000:
                    for i in range(0, len(reply_text), 4000):
                        await update.message.reply_text(reply_text[i:i+4000])
                else:
                    # Добавляем информацию о модели (опционально)
                    if model_used != "unknown":
                        reply_text += f"\n\n---\n🤖 *Модель: {model_used}*"
                    await update.message.reply_text(reply_text, parse_mode="Markdown")
                    
        except Exception as e:
            await update.message.reply_text(f"🔥 Ошибка: {e}")
            print(f"Error: {e}, Response: {response}")
    
    def run(self):
        print("🚀 Бот запущен с интеллектуальным переключением моделей!")
        print(f"📋 Доступно моделей: {len(FREE_MODELS)}")
        print("🔄 При лимитах будет автоматическое переключение")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


# ==================== ТОЧКА ВХОДА ====================
if __name__ == "__main__":
    # Проверка ключей
    if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("⚠️ Укажите TELEGRAM_BOT_TOKEN в начале файла!")
    elif OPENROUTER_API_KEY == "sk-or-v1-YOUR_OPENROUTER_KEY_HERE":
        print("⚠️ Укажите OPENROUTER_API_KEY в начале файла!")
    else:
        bot = TelegramBot(TELEGRAM_BOT_TOKEN, OPENROUTER_API_KEY)
        bot.run()
