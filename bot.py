import os
import logging
import asyncio
import requests
import re
import json
import base64
import time
from urllib.parse import quote_plus
from html.parser import HTMLParser
from flask import Flask, request
import telebot

# ===== НАСТРОЙКА ЛОГОВ =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== ПРОВЕРКА КЛЮЧЕЙ =====
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
RENDER_API_KEY = os.environ.get("RENDER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# ===== ДИАГНОСТИКА =====
logger.info("=" * 50)
logger.info("DIAGNOSTIC START")
logger.info(f"TELEGRAM_TOKEN exists: {bool(TELEGRAM_TOKEN)}")
logger.info(f"OPENROUTER_API_KEY exists: {bool(OPENROUTER_API_KEY)}")
logger.info(f"GITHUB_TOKEN exists: {bool(GITHUB_TOKEN)}")
logger.info(f"RENDER_API_KEY exists: {bool(RENDER_API_KEY)}")
if RENDER_API_KEY:
    logger.info(f"RENDER_API_KEY first 5 chars: {RENDER_API_KEY[:5]}")
    logger.info(f"RENDER_API_KEY length: {len(RENDER_API_KEY)}")
else:
    logger.warning("RENDER_API_KEY NOT FOUND in environment variables!")
logger.info("=" * 50)

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

# ===== СОЗДАНИЕ БОТА И FLASK =====
bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# ===== АКТУАЛЬНЫЙ СПИСОК БЕСПЛАТНЫХ МОДЕЛЕЙ =====
FREE_MODELS = [
    "openrouter/free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-ultra:free",
    "openai/gpt-oss-120b:free",
    "openai/gpt-oss-20b:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "z-ai/glm-4.5-air:free",
    "poolside/laguna-m1:free",
    "poolside/laguna-xs2:free",
    "moonshotai/kimi-k2.6:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "nvidia/nemotron-3-nano-omni:free",
    "qwen/qwen3-coder:free",
]

def ask_ai(prompt, model_index=0):
    if model_index >= len(FREE_MODELS):
        return "😵 Извините, все бесплатные модели временно недоступны. Попробуйте позже."
    
    model = FREE_MODELS[model_index]
    logger.info(f"Пробуем модель: {model}")
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000,
        "temperature": 0.7,
    }
    
    try:
        response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=45)
        
        if response.status_code == 200:
            result = response.json()
            answer = result["choices"][0]["message"]["content"]
            logger.info(f"✅ Модель {model} ответила успешно")
            return answer
        
        elif response.status_code == 429:
            logger.warning(f"⚠️ Модель {model}: лимит запросов (429), переключаем...")
            return ask_ai(prompt, model_index + 1)
        
        elif response.status_code == 402:
            logger.warning(f"⚠️ Модель {model}: требуется оплата (402), переключаем...")
            return ask_ai(prompt, model_index + 1)
        
        else:
            logger.warning(f"⚠️ Модель {model}: ошибка {response.status_code}, переключаем...")
            return ask_ai(prompt, model_index + 1)
            
    except requests.exceptions.Timeout:
        logger.warning(f"⚠️ Модель {model}: таймаут, переключаем...")
        return ask_ai(prompt, model_index + 1)
    except Exception as e:
        logger.error(f"❌ Модель {model}: исключение {e}, переключаем...")
        return ask_ai(prompt, model_index + 1)


# ===== ФУНКЦИИ ДЛЯ GITHUB =====
def github_get_file(repo: str, path: str, branch: str = "main") -> dict:
    if not GITHUB_TOKEN:
        return {"error": "GITHUB_TOKEN не настроен"}
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            return {"success": True, "content": content, "sha": data["sha"]}
        return {"error": f"Ошибка {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def github_update_file(repo: str, path: str, content: str, commit_message: str, branch: str = "main") -> dict:
    if not GITHUB_TOKEN:
        return {"error": "GITHUB_TOKEN не настроен"}
    current = github_get_file(repo, path, branch)
    sha = current.get("sha") if "sha" in current else None
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    payload = {"message": commit_message, "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"), "branch": branch}
    if sha:
        payload["sha"] = sha
    try:
        resp = requests.put(url, headers=headers, json=payload, timeout=30)
        if resp.status_code in (200, 201):
            return {"success": True, "commit": resp.json()["commit"]["sha"]}
        return {"error": f"Ошибка {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def github_list_repos() -> list:
    if not GITHUB_TOKEN:
        return []
    url = "https://api.github.com/user/repos?per_page=10"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return [{"name": r["name"], "full_name": r["full_name"], "url": r["html_url"]} for r in resp.json()]
        return []
    except Exception:
        return []


# ===== ФУНКЦИИ ДЛЯ RENDER =====
def render_list_services() -> list:
    if not RENDER_API_KEY:
        logger.error("RENDER_API_KEY не настроен в render_list_services")
        return []
    url = "https://api.render.com/v1/services"
    headers = {"Authorization": f"Bearer {RENDER_API_KEY}"}
    try:
        logger.info(f"Запрос к Render API: {url}")
        resp = requests.get(url, headers=headers, timeout=30)
        logger.info(f"Ответ Render API: статус {resp.status_code}")
        if resp.status_code == 200:
            return [{"id": s["id"], "name": s["name"], "url": s.get("serviceDetails", {}).get("url", "N/A")} for s in resp.json()]
        else:
            logger.error(f"Ошибка Render API: {resp.text}")
        return []
    except Exception as e:
        logger.error(f"Исключение в render_list_services: {e}")
        return []

def render_restart_service(service_id: str) -> dict:
    if not RENDER_API_KEY:
        return {"error": "RENDER_API_KEY не настроен"}
    url = f"https://api.render.com/v1/services/{service_id}/restart"
    headers = {"Authorization": f"Bearer {RENDER_API_KEY}"}
    try:
        resp = requests.post(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return {"success": True}
        return {"error": f"Ошибка {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def render_rerun_service(service_id: str) -> dict:
    if not RENDER_API_KEY:
        return {"error": "RENDER_API_KEY не настроен"}
    url = f"https://api.render.com/v1/services/{service_id}/deploys"
    headers = {"Authorization": f"Bearer {RENDER_API_KEY}", "Content-Type": "application/json"}
    try:
        resp = requests.post(url, headers=headers, json={"clearCache": "do_not_clear"}, timeout=30)
        if resp.status_code == 201:
            return {"success": True}
        return {"error": f"Ошибка {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def render_set_env_var(service_id: str, key: str, value: str) -> dict:
    if not RENDER_API_KEY:
        return {"error": "RENDER_API_KEY не настроен"}
    url = f"https://api.render.com/v1/services/{service_id}/env-vars"
    headers = {"Authorization": f"Bearer {RENDER_API_KEY}", "Content-Type": "application/json"}
    payload = [{"key": key, "value": value}]
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 201:
            return {"success": True}
        return {"error": f"Ошибка {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}


# ===== КОМАНДА /setup - АГЕНТ САМ СТАВИТ CAMOUFOX НА RENDER =====
def agent_install_camoufox_on_render(service_name: str = None) -> dict:
    """Агент сам заходит на Render и устанавливает Camoufox"""
    logger.info("🦊 Агент начал установку Camoufox на Render...")
    
    if not RENDER_API_KEY:
        return {"error": "RENDER_API_KEY не настроен в переменных окружения"}
    
    # 1. Получаем список сервисов
    services = render_list_services()
    if not services:
        return {"error": "Нет сервисов на Render. Проверь что API ключ правильный и есть сервисы"}
    
    # 2. Находим нужный сервис
    target_service = None
    if service_name:
        target_service = next((s for s in services if s["name"].lower() == service_name.lower()), None)
    else:
        target_service = services[0] if services else None
    
    if not target_service:
        return {"error": f"Сервис '{service_name}' не найден. Доступные: {', '.join([s['name'] for s in services])}"}
    
    logger.info(f"📡 Найден сервис: {target_service['name']} (ID: {target_service['id']})")
    
    # 3. Добавляем переменные окружения для Camoufox
    camouflage_envs = [
        {"key": "CAMOUFOX_ENABLED", "value": "true"},
        {"key": "CAMOUFOX_HEADLESS", "value": "true"},
        {"key": "CAMOUFOX_HUMANIZE", "value": "true"},
        {"key": "CAMOUFOX_BLOCK_WEBRTC", "value": "true"},
        {"key": "CAMOUFOX_GEOIP", "value": "true"},
    ]
    
    added_count = 0
    for env in camouflage_envs:
        result = render_set_env_var(target_service["id"], env["key"], env["value"])
        if "success" in result:
            added_count += 1
            logger.info(f"✅ Добавлена переменная: {env['key']}")
    
    # 4. Перезапускаем сервис
    restart_result = render_restart_service(target_service["id"])
    if "success" in restart_result:
        logger.info(f"🔄 Сервис {target_service['name']} перезапущен")
    
    return {
        "success": True,
        "service": target_service["name"],
        "service_url": target_service["url"],
        "message": "Camoufox установлен и настроен на Render!",
        "env_vars_added": added_count
    }


# ===== КОМАНДА ДЛЯ ПРОВЕРКИ КЛЮЧА =====
@bot.message_handler(commands=['check_key'])
def check_key(message):
    key = os.environ.get("RENDER_API_KEY")
    if key:
        bot.reply_to(message, f"✅ RENDER_API_KEY найден в переменных!\n\nПервые 5 символов: `{key[:5]}...`\nДлина: {len(key)}", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ RENDER_API_KEY НЕ найден в переменных окружения!\n\nПроверь:\n1. Вкладка Environment в Render\n2. Название переменной: `RENDER_API_KEY`\n3. Нажми Save Changes и перезапусти сервис")

@bot.message_handler(commands=['test_render_api'])
def test_render_api(message):
    """Тест прямого запроса к Render API"""
    key = os.environ.get("RENDER_API_KEY")
    if not key:
        bot.reply_to(message, "❌ RENDER_API_KEY не найден")
        return
    
    status_msg = bot.reply_to(message, "📡 Тестирую подключение к Render API...")
    
    try:
        headers = {"Authorization": f"Bearer {key}"}
        resp = requests.get("https://api.render.com/v1/services", headers=headers, timeout=30)
        
        if resp.status_code == 200:
            services = resp.json()
            if services:
                names = [s["name"] for s in services[:5]]
                bot.edit_message_text(
                    f"✅ **Render API работает!**\n\n"
                    f"Статус: {resp.status_code}\n"
                    f"Найдено сервисов: {len(services)}\n"
                    f"Первые 5: {', '.join(names)}",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                    parse_mode="Markdown"
                )
            else:
                bot.edit_message_text(
                    f"✅ Render API работает, но сервисов нет\n\nСтатус: {resp.status_code}",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id
                )
        else:
            bot.edit_message_text(
                f"❌ **Ошибка Render API**\n\n"
                f"Статус: {resp.status_code}\n"
                f"Ответ: {resp.text[:200]}",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode="Markdown"
            )
    except Exception as e:
        bot.edit_message_text(
            f"❌ **Исключение:** {str(e)}",
            chat_id=message.chat.id,
            message_id=status_msg.message_id
        )


@bot.message_handler(commands=['setup'])
def setup_command(message):
    """Агент сам подключается к Render и устанавливает Camoufox"""
    args = message.text.replace('/setup', '').strip().split()
    service_name = args[0] if args else None
    
    status_msg = bot.reply_to(message, "🦊 Агент подключается к Render и устанавливает Camoufox...\n\n⏱️ Это может занять 10-20 секунд")
    
    result = agent_install_camoufox_on_render(service_name)
    
    if "success" in result:
        bot.edit_message_text(
            f"✅ **{result['message']}**\n\n"
            f"📡 **Сервис:** {result['service']}\n"
            f"🔗 **URL:** {result['service_url']}\n"
            f"📊 **Добавлено переменных:** {result['env_vars_added']}/5\n\n"
            f"🔄 Сервис перезапущен. Camoufox готов к использованию через 1-2 минуты.",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode="Markdown"
        )
    else:
        bot.edit_message_text(
            f"❌ **Ошибка:** {result.get('error')}\n\n"
            f"Проверь:\n"
            f"• RENDER_API_KEY в переменных Render\n"
            f"• Название переменной: `RENDER_API_KEY`\n"
            f"• Ключ должен начинаться с `rnd_`\n\n"
            f"Попробуй `/test_render_api` для диагностики",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode="Markdown"
        )


@bot.message_handler(commands=['setup_full'])
def setup_full_command(message):
    """Агент: обновляет код на GitHub И устанавливает Camoufox на Render"""
    args = message.text.replace('/setup_full', '').strip().split()
    
    if len(args) < 2:
        bot.reply_to(
            message,
            "❌ Использование: /setup_full username/repo имя_сервиса\n\n"
            "Пример: /setup_full mygithub/telegram-bot my-bot-on-render"
        )
        return
    
    repo = args[0]
    service_name = args[1]
    
    status_msg = bot.reply_to(message, "🚀 Агент начал полную настройку...\n\n⏱️ Это может занять 1-2 минуты")
    
    results = []
    
    # Шаг 1: Проверяем GitHub токен
    if not GITHUB_TOKEN:
        results.append("❌ GitHub: GITHUB_TOKEN не настроен в переменных Render")
    else:
        results.append("✅ GitHub: токен найден")
    
    # Шаг 2: Проверяем Render токен
    if not RENDER_API_KEY:
        results.append("❌ Render: RENDER_API_KEY не настроен в переменных Render")
    else:
        results.append("✅ Render: токен найден")
    
    # Шаг 3: Устанавливаем Camoufox на Render
    if RENDER_API_KEY:
        render_result = agent_install_camoufox_on_render(service_name)
        
        if "success" in render_result:
            results.append(f"✅ Render: Camoufox установлен на {render_result['service']}")
            results.append(f"📊 Добавлено переменных: {render_result['env_vars_added']}/5")
        else:
            results.append(f"❌ Render: {render_result.get('error')}")
    
    bot.edit_message_text(
        "🔧 **Результаты настройки:**\n\n" + "\n".join(results) + "\n\n"
        "📌 **Что дальше:**\n"
        "• Перезапусти сервис на Render вручную или подожди 2 минуты\n"
        "• Camoufox готов обходить блокировки Google",
        chat_id=message.chat.id,
        message_id=status_msg.message_id,
        parse_mode="Markdown"
    )


# ===== ФУНКЦИЯ ДЛЯ БРАУЗЕРА =====
class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
    def handle_data(self, d):
        self.text.append(d)
    def get_data(self):
        return ' '.join(self.text)


async def browse_lightpanda(task: str) -> str:
    """Работает с любым запросом: URL, поиск, вопрос"""
    try:
        urls = re.findall(r'https?://[^\s]+', task)
        if urls:
            url = urls[0]
            resp = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
            if resp.status_code == 200:
                stripper = MLStripper()
                stripper.feed(resp.text)
                text = stripper.get_data()
                text = ' '.join(text.split())[:2000]
                return f"📄 Содержимое {url}:\n\n{text}..."
            return f"❌ Ошибка загрузки {url}"
        
        query = quote_plus(task)
        search_url = f"https://html.duckduckgo.com/html/?q={query}"
        resp = requests.get(search_url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        
        if resp.status_code == 200:
            titles = re.findall(r'<a class="result__a"[^>]*>([^<]+)</a>', resp.text)
            snippets = re.findall(r'<a class="result__snippet"[^>]*>([^<]+)</a>', resp.text)
            
            results = []
            for i in range(min(3, len(titles))):
                title = titles[i] if i < len(titles) else ""
                snippet = snippets[i] if i < len(snippets) else ""
                if title:
                    results.append(f"🔹 {title}\n   {snippet[:150]}...")
            
            if results:
                return f"🔍 Результаты поиска:\n\n" + "\n\n".join(results)
        
        return await ai_fallback(task)
        
    except Exception as e:
        logger.error(f"Ошибка в browse: {e}")
        return await ai_fallback(task)


async def ai_fallback(task: str) -> str:
    """Резервный ответ через ИИ"""
    if not OPENROUTER_API_KEY:
        return f"🌐 Не удалось обработать запрос. API ключ не настроен."
    
    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "openrouter/free",
            "messages": [{"role": "user", "content": task}],
            "max_tokens": 500,
        }
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            answer = resp.json()["choices"][0]["message"]["content"]
            return f"🤖 {answer}"
        return f"❌ Не удалось обработать запрос"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"


# ===== ОБРАБОТЧИКИ КОМАНД ТЕЛЕГРАМ =====
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(
        message,
        "✅ Бот-агент с доступом к Render и GitHub!\n\n"
        "📌 **Команды:**\n"
        "/check_key - проверить наличие RENDER_API_KEY\n"
        "/test_render_api - тест подключения к Render API\n"
        "/setup [имя_сервиса] - установить Camoufox на Render\n"
        "/setup_full репо сервис - полная настройка\n"
        "/ai [вопрос] - спросить ИИ\n"
        "/browse [запрос] - поиск в интернете\n"
        "/github list - список репозиториев\n"
        "/render list - список сервисов\n"
        "/models - список моделей ИИ\n"
        "/help - помощь",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['help'])
def help_command(message):
    bot.reply_to(
        message,
        "🤖 **Команды бота:**\n\n"
        "**🔑 Диагностика:**\n"
        "/check_key - проверить наличие RENDER_API_KEY\n"
        "/test_render_api - тест подключения к Render API\n\n"
        "**🦊 Установка Camoufox:**\n"
        "/setup - установить на первый сервис\n"
        "/setup имя - установить на конкретный сервис\n"
        "/setup_full репо сервис - полная настройка\n\n"
        "**🧠 ИИ и поиск:**\n"
        "/ai [вопрос] - задать вопрос ИИ\n"
        "/browse [запрос] - поиск в интернете\n\n"
        "**📁 GitHub:**\n"
        "/github list - список репозиториев\n\n"
        "**🖥️ Render:**\n"
        "/render list - список сервисов\n\n"
        "**📊 Прочее:**\n"
        "/models - список моделей ИИ",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['ai'])
def ai_command(message):
    user_text = message.text.replace('/ai', '').strip()
    if not user_text:
        bot.reply_to(message, "❌ Напиши вопрос после /ai")
        return
    
    bot.send_chat_action(message.chat.id, 'typing')
    status_msg = bot.reply_to(message, "🤔 Думаю...")
    answer = ask_ai(user_text)
    bot.edit_message_text(answer, chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['browse'])
def browse_command(message):
    user_task = message.text.replace('/browse', '').strip()
    if not user_task:
        bot.reply_to(message, "❌ Напиши запрос после /browse")
        return
    
    bot.send_chat_action(message.chat.id, 'typing')
    status_msg = bot.reply_to(message, "🔍 Ищу...")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(browse_lightpanda(user_task))
        if len(result) > 4000:
            result = result[:4000] + "..."
        bot.edit_message_text(result, chat_id=message.chat.id, message_id=status_msg.message_id)
    except Exception as e:
        logger.error(f"Ошибка в browse_command: {e}")
        bot.edit_message_text(f"❌ Ошибка: {str(e)}", chat_id=message.chat.id, message_id=status_msg.message_id)
    finally:
        loop.close()

@bot.message_handler(commands=['github'])
def github_command(message):
    args = message.text.replace('/github', '').strip().split()
    if not args or args[0] != "list":
        bot.reply_to(message, "📁 Использование: /github list")
        return
    
    repos = github_list_repos()
    if not repos:
        bot.reply_to(message, "❌ Нет репозиториев или GITHUB_TOKEN не настроен")
        return
    
    result = "📁 **Ваши репозитории:**\n\n" + "\n".join([f"• {r['name']}" for r in repos[:10]])
    bot.reply_to(message, result, parse_mode="Markdown")

@bot.message_handler(commands=['render'])
def render_command(message):
    args = message.text.replace('/render', '').strip().split()
    if not args or args[0] != "list":
        bot.reply_to(message, "🖥️ Использование: /render list")
        return
    
    services = render_list_services()
    if not services:
        bot.reply_to(message, "❌ Нет сервисов или RENDER_API_KEY не настроен")
        return
    
    result = "🖥️ **Сервисы на Render:**\n\n" + "\n".join([f"• {s['name']} - {s['url']}" for s in services])
    bot.reply_to(message, result, parse_mode="Markdown")

@bot.message_handler(commands=['models'])
def models_command(message):
    models_list = "\n".join([f"• {m.replace(':free', '')}" for m in FREE_MODELS])
    bot.reply_to(
        message,
        f"🤖 **Доступные модели:**\n\n{models_list}\n\n"
        f"📊 Всего: {len(FREE_MODELS)} моделей\n"
        f"🔄 При лимите автоматическое переключение",
        parse_mode="Markdown"
    )


# ===== ВЕБХУК ДЛЯ TELEGRAM =====
@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        json_str = request.stream.read().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return 'ok', 200
    except Exception as e:
        logger.error(f"Ошибка вебхука: {e}")
        return 'error', 500

@app.route('/health')
def health():
    return 'OK', 200

@app.route('/')
def index():
    return 'Telegram Bot with Camoufox Setup Agent is running!', 200


# ===== ЗАПУСК =====
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    render_url = os.environ.get('RENDER_EXTERNAL_URL')
    
    if not render_url:
        render_url = f"http://localhost:{port}"
        logger.warning(f"RENDER_EXTERNAL_URL не найден, используем {render_url}")
    
    webhook_url = f"{render_url}/{TELEGRAM_TOKEN}"
    
    logger.info("Удаляем старый вебхук...")
    bot.remove_webhook()
    
    logger.info(f"Устанавливаем новый вебхук: {webhook_url}")
    bot.set_webhook(url=webhook_url)
    
    logger.info(f"🚀 Запускаем Flask сервер на порту {port}")
    app.run(host='0.0.0.0', port=port)
