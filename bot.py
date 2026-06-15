import os
import logging
import asyncio
import requests
import re
import json
import base64
import time
import traceback
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

# ===== ID СЕРВИСА =====
BUGAGA_SERVICE_ID = "srv-d8n7h40js32c73dcoi8g"
BUGAGA_SERVICE_NAME = "Bugaga"
BUGAGA_SERVICE_URL = "https://bugaga.onrender.com"

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
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            services_list = []
            
            if isinstance(data, list):
                for item in data:
                    service = item.get("service", item)
                    service_id = service.get("id")
                    service_name = service.get("name")
                    service_url = service.get("url", "N/A")
                    
                    if service_id and service_name:
                        services_list.append({
                            "id": service_id,
                            "name": service_name,
                            "url": service_url
                        })
            return services_list
        else:
            logger.error(f"Ошибка Render API: {resp.status_code}")
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

def render_set_env_vars(service_id: str, env_vars: list) -> dict:
    """Устанавливает несколько переменных окружения за раз (PUT)"""
    if not RENDER_API_KEY:
        return {"error": "RENDER_API_KEY не настроен"}
    
    url = f"https://api.render.com/v1/services/{service_id}/env-vars"
    headers = {
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        resp = requests.put(url, headers=headers, json=env_vars, timeout=30)
        if resp.status_code in (200, 201):
            return {"success": True}
        return {"error": f"Ошибка {resp.status_code}: {resp.text[:100]}"}
    except Exception as e:
        return {"error": str(e)}


# ===== УСТАНОВКА CAMOUFOX =====
def install_camoufox_on_bugaga() -> dict:
    """Прямая установка Camoufox на сервис Bugaga"""
    logger.info("🦊 Установка Camoufox на Bugaga...")
    
    if not RENDER_API_KEY:
        return {"error": "RENDER_API_KEY не настроен", "success": False, "env_vars_added": 0, "errors": []}
    
    env_vars = [
        {"key": "CAMOUFOX_ENABLED", "value": "true"},
        {"key": "CAMOUFOX_HEADLESS", "value": "true"},
        {"key": "CAMOUFOX_HUMANIZE", "value": "true"},
        {"key": "CAMOUFOX_BLOCK_WEBRTC", "value": "true"},
        {"key": "CAMOUFOX_GEOIP", "value": "true"},
    ]
    
    result = render_set_env_vars(BUGAGA_SERVICE_ID, env_vars)
    
    if "success" in result:
        logger.info("✅ Переменные Camoufox добавлены")
        render_restart_service(BUGAGA_SERVICE_ID)
        return {
            "success": True,
            "service_name": BUGAGA_SERVICE_NAME,
            "service_url": BUGAGA_SERVICE_URL,
            "env_vars_added": 5,
            "errors": []
        }
    else:
        return {
            "success": False,
            "service_name": BUGAGA_SERVICE_NAME,
            "service_url": BUGAGA_SERVICE_URL,
            "env_vars_added": 0,
            "errors": [result.get("error", "Неизвестная ошибка")]
        }


# ===== ПОИСК В GOOGLE ЧЕРЕЗ CAMOUFOX =====
async def search_google_camoufox(query: str) -> str:
    """
    Ищет в Google через Camoufox — обходит блокировки Google
    """
    try:
        from camoufox.sync_api import Camoufox
        
        with Camoufox(
            headless=True,
            humanize=True,
            block_webrtc=True,
            geoip=True,
        ) as browser:
            page = browser.new_page()
            
            search_url = f"https://www.google.com/search?q={quote_plus(query)}"
            
            page.goto(search_url, wait_until="networkidle")
            page.wait_for_selector("div#search", timeout=15000)
            
            results = []
            for result in page.query_selector_all("div.g")[:5]:
                title_elem = result.query_selector("h3")
                link_elem = result.query_selector("a")
                snippet_elem = result.query_selector("div.VwiC3b")
                
                title = title_elem.inner_text() if title_elem else ""
                link = link_elem.get_attribute("href") if link_elem else ""
                snippet = snippet_elem.inner_text()[:200] if snippet_elem else ""
                
                if title and link:
                    results.append(f"🔹 **{title}**\n   📎 {link}\n   📝 {snippet}...")
            
            if results:
                return f"🔍 **Результаты Google для «{query}»:**\n\n" + "\n\n".join(results)
            else:
                return "❌ Ничего не найдено"
                
    except ImportError:
        return "❌ Camoufox не установлен. Установи через: pip install camoufox"
    except Exception as e:
        logger.error(f"Camoufox error: {e}")
        return f"❌ Ошибка при поиске: {str(e)}"


# ===== ФУНКЦИЯ ДЛЯ БРАУЗЕРА (DUCKDUCKGO) =====
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
        "✅ **Бот-агент с Camoufox!**\n\n"
        "📌 **Команды:**\n"
        "/google [запрос] - поиск в Google (обходит блокировки)\n"
        "/ai [вопрос] - спросить ИИ\n"
        "/browse [запрос] - быстрый поиск (DuckDuckGo)\n"
        "/setup_bugaga - установить Camoufox на Render\n"
        "/check_key - проверить ключи\n"
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
        "**🦊 Поиск в Google:**\n"
        "/google [запрос] - поиск через Google (Camoufox, обходит блокировки)\n\n"
        "**🧠 ИИ и поиск:**\n"
        "/ai [вопрос] - задать вопрос ИИ\n"
        "/browse [запрос] - быстрый поиск (DuckDuckGo)\n\n"
        "**🔧 Настройка:**\n"
        "/setup_bugaga - установить Camoufox на Render\n"
        "/check_key - проверить ключи\n\n"
        "**📁 GitHub:**\n"
        "/github list - список репозиториев\n\n"
        "**🖥️ Render:**\n"
        "/render list - список сервисов\n\n"
        "**📊 Прочее:**\n"
        "/models - список моделей ИИ",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['setup_bugaga'])
def setup_bugaga(message):
    """Установка Camoufox на сервис Bugaga"""
    status_msg = bot.reply_to(message, "🦊 Устанавливаю Camoufox на Bugaga...\n\n⏱️ Это может занять 10-20 секунд")
    
    result = install_camoufox_on_bugaga()
    
    if result["success"]:
        response = (
            f"✅ **Camoufox успешно установлен!**\n\n"
            f"📡 **Сервис:** {result['service_name']}\n"
            f"🔗 **URL:** {result['service_url']}\n"
            f"📊 **Добавлено переменных:** {result['env_vars_added']}/5\n\n"
            f"🔄 Сервис перезапущен.\n"
            f"🌐 Camoufox готов обходить блокировки Google!"
        )
    else:
        response = (
            f"❌ **Ошибка установки**\n\n"
            f"Добавлено переменных: {result['env_vars_added']}/5\n"
        )
        if result['errors']:
            response += f"\n**Ошибки:**\n" + "\n".join(result['errors'])
    
    bot.edit_message_text(
        response,
        chat_id=message.chat.id,
        message_id=status_msg.message_id,
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['google'])
def google_command(message):
    """Поиск в Google через Camoufox (обходит блокировки)"""
    query = message.text.replace('/google', '').strip()
    
    if not query:
        bot.reply_to(
            message,
            "❌ Напиши запрос после /google\n\n"
            "Пример: `/google как сделать пиццу`",
            parse_mode="Markdown"
        )
        return
    
    bot.send_chat_action(message.chat.id, 'typing')
    status_msg = bot.reply_to(message, f"🦊 Ищу в Google: {query[:50]}...\n\n⏱️ Это может занять 10-15 секунд")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(search_google_camoufox(query))
        if len(result) > 4000:
            result = result[:4000] + "..."
        bot.edit_message_text(
            result,
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка в google_command: {e}")
        bot.edit_message_text(
            f"❌ Ошибка: {str(e)}",
            chat_id=message.chat.id,
            message_id=status_msg.message_id
        )
    finally:
        loop.close()

@bot.message_handler(commands=['check_key'])
def check_key(message):
    key = os.environ.get("RENDER_API_KEY")
    if key:
        bot.reply_to(message, f"✅ RENDER_API_KEY найден!\n\nПервые 5 символов: `{key[:5]}...`\nДлина: {len(key)}", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ RENDER_API_KEY НЕ найден в переменных окружения!")

@bot.message_handler(commands=['test_render'])
def test_render(message):
    """Тест Render API"""
    if not RENDER_API_KEY:
        bot.reply_to(message, "❌ RENDER_API_KEY не найден")
        return
    
    status_msg = bot.reply_to(message, "📡 Тестирую Render API...")
    
    try:
        headers = {"Authorization": f"Bearer {RENDER_API_KEY}"}
        resp = requests.get("https://api.render.com/v1/services", headers=headers, timeout=30)
        
        if resp.status_code == 200:
            data = resp.json()
            bot.edit_message_text(
                f"✅ **Render API работает!**\n\n"
                f"Статус: {resp.status_code}\n"
                f"Найдено сервисов: {len(data)}",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode="Markdown"
            )
        else:
            bot.edit_message_text(
                f"❌ Ошибка {resp.status_code}",
                chat_id=message.chat.id,
                message_id=status_msg.message_id
            )
    except Exception as e:
        bot.edit_message_text(
            f"❌ Ошибка: {str(e)}",
            chat_id=message.chat.id,
            message_id=status_msg.message_id
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


# ===== ВЕБХУК =====
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
    return 'Telegram Bot with Camoufox is running!', 200


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
