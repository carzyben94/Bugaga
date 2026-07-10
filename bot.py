import asyncio
import logging
import os
import base64
import requests
import json
import sqlite3
import re
import psutil
import platform
from datetime import datetime, timedelta
from PIL import Image
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
if not AGNES_API_KEY:
    logger.warning("⚠️ AGNES_API_KEY не установлен!")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
GITHUB_PATH = "agent_memory.json"

if not GITHUB_TOKEN or not GITHUB_REPO:
    logger.warning("⚠️ GITHUB_TOKEN или GITHUB_REPO не установлены!")

CHROME_PATH = "/usr/bin/google-chrome"
AGNES_API_URL = "https://apihub.agnes-ai.com/v1/chat/completions"
AGNES_IMAGE_URL = "https://apihub.agnes-ai.com/v1/images/generations"

# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ---
browser_instance = None
tab_instance = None
current_url = None
page_title = None
page_content = None
start_time = datetime.now()
PENDING_ACTIONS = {}

# --- ФУНКЦИИ РАБОТЫ С GITHUB ---
def load_all_memory():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return {}
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            content = response.json()['content']
            decoded = base64.b64decode(content).decode('utf-8')
            return json.loads(decoded)
        return {}
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки из GitHub: {e}")
        return {}

def save_all_memory(data):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return False
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        response = requests.get(url, headers=headers)
        sha = response.json().get('sha') if response.status_code == 200 else None
        content = json.dumps(data, indent=2, ensure_ascii=False)
        encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        payload = {"message": f"Update agent memory {datetime.now().strftime('%Y-%m-%d %H:%M')}", "content": encoded, "sha": sha}
        response = requests.put(url, json=payload, headers=headers)
        if response.status_code in [200, 201]:
            logger.info("✅ Память сохранена в GitHub")
            return True
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения в GitHub: {e}")
        return False

def load_user_memory(user_id):
    all_data = load_all_memory()
    user_key = str(user_id)
    if user_key not in all_data:
        return {"commands": [], "experiments": [], "learned": 0, "created_at": datetime.now().isoformat()}
    return all_data[user_key]

def save_user_memory(user_id, data):
    all_data = load_all_memory()
    all_data[str(user_id)] = data
    return save_all_memory(all_data)

def save_learning(user_id, command, action, context, success):
    data = load_user_memory(user_id)
    data['commands'].append({'command': command, 'action': action, 'context': context, 'success': success, 'created_at': datetime.now().isoformat()})
    data['learned'] = len([c for c in data['commands'] if c['success']])
    if len(data['commands']) > 100:
        data['commands'] = data['commands'][-100:]
    return save_user_memory(user_id, data)

def get_learned_actions(user_id, command):
    data = load_user_memory(user_id)
    results = []
    for item in data.get('commands', []):
        if command.lower() in item['command'].lower() and item['success']:
            results.append((item['action'], item['context']))
    return results[:5]

def save_experiment_memory(user_id, goal, attempts, best_result, status):
    data = load_user_memory(user_id)
    data['experiments'].append({'goal': goal, 'attempts': attempts, 'best_result': best_result, 'status': status, 'created_at': datetime.now().isoformat()})
    if len(data['experiments']) > 50:
        data['experiments'] = data['experiments'][-50:]
    return save_user_memory(user_id, data)

def get_experiments_memory(user_id):
    data = load_user_memory(user_id)
    return data.get('experiments', [])

# --- ФУНКЦИИ БРАУЗЕРА ---
def get_browser_options():
    options = ChromiumOptions()
    options.binary_location = CHROME_PATH
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.start_timeout = 30
    return options

async def open_browser():
    global browser_instance, tab_instance
    try:
        if browser_instance is None:
            options = get_browser_options()
            browser_instance = Chrome(options=options)
            await browser_instance.start()
            tab_instance = await browser_instance.start()
            logger.info("✅ Браузер открыт")
            return True
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False

async def close_browser():
    global browser_instance, tab_instance
    try:
        if browser_instance is not None:
            await browser_instance.stop()
            browser_instance = None
            tab_instance = None
            logger.info("✅ Браузер закрыт")
            return True
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False

async def go_to_url(url: str):
    global tab_instance, current_url, page_title, page_content
    try:
        if tab_instance is None:
            return False, "Браузер не открыт"
        await tab_instance.go_to(url)
        current_url = url
        page_title = await tab_instance.title
        try:
            page_content = await tab_instance.get_page_text()
        except AttributeError:
            page_content = "Текст страницы не доступен"
        return True, f"Перешел на {url}"
    except Exception as e:
        return False, str(e)

async def take_screenshot():
    global tab_instance
    try:
        if tab_instance is None:
            return None, "Браузер не открыт"
        screenshot_data = await tab_instance.take_screenshot(beyond_viewport=True, as_base64=True)
        return screenshot_data, None
    except Exception as e:
        return None, str(e)

async def get_page_info():
    global current_url, page_title, page_content
    return {'url': current_url, 'title': page_title, 'content': page_content[:1000] if page_content else None}

# --- ФУНКЦИЯ ВОЗМОЖНОСТЕЙ АГЕНТА ---
def get_agent_capabilities():
    return """Ты - AI агент, который УПРАВЛЯЕТ БРАУЗЕРОМ через библиотеку Pydoll.

✅ Что ТЫ МОЖЕШЬ делать:
1. Переходить по ссылкам (например: /go vk.com)
2. Делать скриншоты страниц (/screen)
3. Открывать и закрывать браузер (/open_bw, /close_bw)
4. Показывать статус системы (/status)
5. Заменять фон на фото (/bg)
6. Обучаться новым командам (/learn)
7. Экспериментировать с промтами (/experiment)
8. Показывать библиотеку ресурсов (/library)
9. Вести диалог и запоминать историю
10. Сохранять память в GitHub
11. Запоминать частые команды и предлагать обучение
12. Учиться на исправлениях пользователя

❌ ЧЕГО ТЫ НЕ МОЖЕШЬ делать (даже с разрешением):
1. ДОСТУП К ЛИЧНЫМ ДАННЫМ - пароли, файлы пользователя
2. ДЕЙСТВИЯ ВНЕ БРАУЗЕРА - управление приложениями на ПК
3. ЗАГРУЗКА ФАЙЛОВ - скачивание на устройство пользователя
4. РЕАЛЬНЫЕ ПОКУПКИ - платежи и покупки
5. ВЗЛОМ И ПРОНИКНОВЕНИЕ - взлом сайтов, обход защиты
6. РЕДАКТИРОВАНИЕ КОДА - изменение своего кода или кода бота

⚠️ ПРАВИЛА:
1. Если просят НЕВОЗМОЖНОЕ - ВЕЖЛИВО объясни и предложи альтернативу
2. Если просят ВРЕДНОЕ - ОТКАЖИСЬ
3. Если просят ЛИЧНЫЕ ДАННЫЕ - скажи, что их нет
4. Если НЕ ЗНАЕШЬ - честно признайся

🔄 САМООБУЧЕНИЕ:
1. Запоминай частые команды - если пользователь повторяет, предложи запомнить
2. Запоминай исправления - когда пользователь поправляет, запоминай правильный вариант
3. Предлагай помощь - если видишь, что пользователь что-то ищет
4. Анализируй поведение - замечай, какие сайты часто открываются

💬 Все команды можно использовать в обычном разговоре:
"перейди на vk.com" или "сделай скриншот"

Помни: Ты - ПОЛЕЗНЫЙ ПОМОЩНИК в ОПРЕДЕЛЕННЫХ ГРАНИЦАХ!"""

def call_agnes_agent(prompt: str, context: dict = None, learning_context: str = None):
    if not AGNES_API_KEY:
        return None, "AGNES_API_KEY не установлен"
    try:
        system_prompt = get_agent_capabilities()
        messages = [{"role": "system", "content": system_prompt}]
        if learning_context:
            messages.append({"role": "system", "content": f"Контекст: {learning_context}"})
        if context:
            messages.append({"role": "user", "content": f"Текущее состояние: URL: {context.get('url', 'Неизвестно')}, Заголовок: {context.get('title', 'Неизвестно')}"})
        messages.append({"role": "user", "content": prompt})
        headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "agnes-2.0-flash", "messages": messages, "max_tokens": 1000}
        response = requests.post(AGNES_API_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content'], None
    except Exception as e:
        logger.error(f"Ошибка Agnes: {e}")
        return None, str(e)

# --- ФУНКЦИЯ ЗАМЕНЫ ФОНА ---
def replace_background(image_data, new_background_prompt: str):
    if not AGNES_API_KEY:
        return None, "AGNES_API_KEY не установлен!"
    try:
        img_b64 = base64.b64encode(image_data).decode('utf-8')
        data_uri = f"data:image/jpeg;base64,{img_b64}"
        headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "agnes-image-2.0-flash", "prompt": f"Replace the background with: {new_background_prompt}. Keep the main subject unchanged.", "size": "1024x1024", "extra_body": {"image": [data_uri], "response_format": "url"}}
        response = requests.post(AGNES_IMAGE_URL, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        result = response.json()
        return result['data'][0]['url'], None
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return None, str(e)

# --- ОБРАБОТЧИК РАЗРЕШЕНИЙ ---
async def request_permission(update, action, details, params=None):
    user_id = update.effective_user.id
    PENDING_ACTIONS[user_id] = {"action": action, "details": details, "params": params, "timestamp": datetime.now().isoformat()}
    keyboard = [[InlineKeyboardButton("✅ Разрешить", callback_data=f"permit_allow_{user_id}"), InlineKeyboardButton("❌ Запретить", callback_data=f"permit_deny_{user_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"⚠️ **Запрос разрешения:**\n\n🔄 Действие: {action}\n📝 Подробности: {details}\n\nРазрешить выполнить?", reply_markup=reply_markup)

async def permit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data.split('_')
    action_type = data[1]
    target_user_id = int(data[2])
    if user_id != target_user_id:
        await query.edit_message_text("❌ Это не ваш запрос!")
        return
    if target_user_id not in PENDING_ACTIONS:
        await query.edit_message_text("⌛️ Запрос уже обработан.")
        return
    pending = PENDING_ACTIONS[target_user_id]
    if action_type == "allow":
        await query.edit_message_text(f"✅ Разрешено! Выполняю: {pending['action']}")
        action_name = pending['action']
        params = pending.get('params', {})
        if action_name == "go_to_url" and 'url' in params:
            success, msg = await go_to_url(params['url'])
            if success:
                screenshot_data, _ = await take_screenshot()
                if screenshot_data:
                    screenshot_bytes = base64.b64decode(screenshot_data)
                    await update.message.reply_photo(screenshot_bytes, caption=f"📸 {msg}")
                await update.message.reply_text(f"✅ {msg}")
        elif action_name == "screenshot":
            screenshot_data, error = await take_screenshot()
            if screenshot_data:
                screenshot_bytes = base64.b64decode(screenshot_data)
                await update.message.reply_photo(screenshot_bytes, caption="📸 Скриншот")
            else:
                await update.message.reply_text(f"❌ {error}")
        elif action_name == "experiment":
            await update.message.reply_text(f"🧪 Начинаю эксперимент: {params.get('goal', '')}")
        elif action_name == "delete_memory":
            user_id = update.effective_user.id
            data = {"commands": [], "experiments": [], "learned": 0, "created_at": datetime.now().isoformat()}
            if save_user_memory(user_id, data):
                await update.message.reply_text("🧹 Память очищена!")
            else:
                await update.message.reply_text("❌ Ошибка очистки памяти")
        del PENDING_ACTIONS[target_user_id]
    elif action_type == "deny":
        await query.edit_message_text(f"❌ Действие '{pending['action']}' запрещено.")
        del PENDING_ACTIONS[target_user_id]

# --- КОМАНДЫ БОТА ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌐 **Браузер:**\n"
        "/status - Статус и показатели агента\n"
        "/open_bw - Открыть браузер\n"
        "/close_bw - Закрыть браузер\n"
        "/screen - Скриншот\n"
        "/go - Перейти на сайт\n"
        "🎨 **Фотошоп:**\n"
        "/bg - Замена фона\n"
        "/clear - Очистить кэш\n"
        "🧪 **Эксперименты:**\n"
        "/experiment <цель> - Эксперимент с промтами\n"
        "/experiments - История экспериментов\n"
        "📚 **Ресурсы:**\n"
        "/library - Библиотека ресурсов\n"
        "/library <категория> - Ресурсы по категории\n"
        "/library find <текст> - Поиск ресурсов\n"
        "🤖 **Агент:**\n"
        "/agent <запрос> - Управление через AI\n"
        "/dialog - Начать диалог\n"
        "/end_dialog - Закончить диалог\n"
        "/clear_dialog - Очистить историю\n"
        "/learn <команда -> действие> - Научить агента\n"
        "/knowledge - Что умеет агент\n"
        "/help_agent <описание> - Помочь агенту\n"
        "/capabilities - Все возможности бота\n"
        "💾 **Память:**\n"
        "/reset_memory - Очистить память агента"
    )

async def capabilities_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 **Мои возможности:**\n\n"
        "🌐 **Браузер:**\n"
        "/go <URL> - Перейти на сайт\n"
        "/screen - Скриншот\n"
        "/open_bw - Открыть браузер\n"
        "/close_bw - Закрыть браузер\n"
        "/status - Статус системы\n\n"
        "🎨 **Фотошоп:**\n"
        "/bg <описание> - Замена фона\n"
        "/clear - Очистить кэш\n\n"
        "🧪 **Эксперименты:**\n"
        "/experiment <цель> - Эксперимент с промтами\n"
        "/experiments - История экспериментов\n\n"
        "📚 **Ресурсы:**\n"
        "/library - Библиотека ресурсов\n"
        "/library find <текст> - Поиск ресурсов\n\n"
        "🤖 **Агент:**\n"
        "/agent <запрос> - Управление через AI\n"
        "/dialog - Начать диалог\n"
        "/end_dialog - Закончить диалог\n"
        "/learn <команда -> действие> - Научить агента\n"
        "/knowledge - Что умеет агент\n"
        "/help_agent <описание> - Помочь агенту\n"
        "/reset_memory - Очистить память\n\n"
        "💾 **Память сохраняется в GitHub!**"
    )

# --- ОСТАЛЬНЫЕ КОМАНДЫ ---
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    browser_status = "🟢 Включен" if browser_instance is not None and tab_instance is not None else "🔴 Выключен"
    user_data = load_user_memory(user_id)
    uptime = datetime.now() - start_time
    uptime_str = str(uptime).split('.')[0]
    try:
        memory = psutil.virtual_memory()
        memory_used = memory.used / (1024**3)
        memory_total = memory.total / (1024**3)
        cpu_percent = psutil.cpu_percent(interval=0.5)
    except:
        memory_used, memory_total, cpu_percent = 0, 0, 0
    agnes_status = "✅ Настроен" if AGNES_API_KEY else "❌ Не настроен"
    github_status = "✅ Подключен" if GITHUB_TOKEN and GITHUB_REPO else "❌ Не подключен"
    response = (
        f"📊 **Статус системы**\n\n"
        f"🖥️ **Браузер:**\n  • Статус: {browser_status}\n  • Путь: {CHROME_PATH}\n\n"
        f"🤖 **Агент:**\n  • Agnes AI: {agnes_status}\n  • Команд выучено: {user_data.get('learned', 0)}\n  • Экспериментов: {len(user_data.get('experiments', []))}\n\n"
        f"💾 **Хранилище:**\n  • GitHub: {github_status}\n  • Команд в памяти: {len(user_data.get('commands', []))}\n\n"
        f"⚙️ **Система:**\n  • Время работы: {uptime_str}\n  • CPU: {cpu_percent}%\n  • Память: {memory_used:.1f}GB / {memory_total:.1f}GB\n\n"
    )
    commands = user_data.get('commands', [])[-3:]
    if commands:
        response += "🔄 **Последние команды:**\n"
        for cmd in commands:
            response += f"  • {cmd.get('command', '')} -> {cmd.get('action', '')[:30]}...\n"
    if user_data.get('learned', 0) < 3:
        response += "\n💡 **Совет:** Научите меня через /learn!"
    if not AGNES_API_KEY:
        response += "\n⚠️ Agnes AI не настроен!"
    if not GITHUB_TOKEN or not GITHUB_REPO:
        response += "\n⚠️ GitHub не настроен!"
    await update.message.reply_text(response)

async def open_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    success = await open_browser()
    await update.message.reply_text("🌐 Браузер открыт ✅" if success else "❌ Не удалось открыть браузер")

async def close_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    success = await close_browser()
    await update.message.reply_text("❌ Браузер закрыт ✅" if success else "❌ Не удалось закрыть браузер")

async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Делаю скриншот...")
    screenshot_data, error = await take_screenshot()
    if error:
        await update.message.reply_text(f"❌ {error}")
    elif screenshot_data:
        screenshot_bytes = base64.b64decode(screenshot_data)
        await update.message.reply_photo(screenshot_bytes, caption="📸 Скриншот")

async def go_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажите URL. Пример: /go https://example.com")
        return
    url = context.args[0]
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    success, msg = await go_to_url(url)
    await update.message.reply_text(f"✅ {msg}" if success else f"❌ {msg}")

async def bg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not AGNES_API_KEY:
        await update.message.reply_text("❌ Agnes AI не настроен.")
        return
    if 'last_image' not in context.user_data:
        await update.message.reply_text("📸 Сначала загрузите картинку!")
        return
    if not context.args:
        await update.message.reply_text("✏️ Напишите описание фона. Пример: /bg beach")
        return
    prompt = ' '.join(context.args)
    await update.message.reply_text(f"🎨 Заменяю фон: {prompt}")
    image_data = context.user_data['last_image']
    result_url, error = replace_background(image_data, prompt)
    if error:
        await update.message.reply_text(f"❌ {error}")
    elif result_url:
        response = requests.get(result_url, timeout=30)
        if response.status_code == 200:
            await update.message.reply_photo(response.content, caption="🖼️ Готово!")
        else:
            await update.message.reply_text(f"❌ Ошибка {response.status_code}")

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'last_image' in context.user_data:
        del context.user_data['last_image']
        await update.message.reply_text("🧹 Кэш очищен!")
    else:
        await update.message.reply_text("📭 Кэш пуст")

async def learn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("📚 /learn <команда> -> <действие>\nПример: /learn вк -> vk.com")
        return
    user_id = update.effective_user.id
    text = ' '.join(context.args)
    if '->' in text:
        parts = text.split('->')
        command = parts[0].strip()
        action = parts[1].strip()
        if save_learning(user_id, command, action, "user_taught", True):
            await update.message.reply_text(f"✅ Запомнил! 💾 Сохранено в GitHub\nКоманда: {command}\nДействие: {action}")
        else:
            await update.message.reply_text(f"✅ Запомнил!\nКоманда: {command}\nДействие: {action}\n⚠️ GitHub не настроен")
    else:
        await update.message.reply_text("❌ Используйте: /learn команда -> действие")

async def knowledge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = load_user_memory(user_id)
    commands = data.get('commands', [])
    experiments = data.get('experiments', [])
    response = "🧠 **Что я умею:**\n\n"
    if commands:
        response += "📚 **Выученные команды:**\n"
        for cmd in commands[-10:]:
            if cmd['success']:
                response += f"• {cmd['command']} -> {cmd['action']}\n"
    if experiments:
        response += "\n🧪 **Эксперименты:**\n"
        for exp in experiments[-3:]:
            response += f"• {exp['goal'][:50]}...\n"
    if not commands and not experiments:
        response = "📭 Я пока ничего не выучил. Научи меня через /learn!"
    response += f"\n\n💾 Всего команд: {len(commands)}\nВсего экспериментов: {len(experiments)}"
    await update.message.reply_text(response)

async def help_agent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("🤝 /help_agent <описание>\nПример: /help_agent нужно нажать кнопку Войти")
        return
    user_id = update.effective_user.id
    help_text = ' '.join(context.args)
    if save_learning(user_id, help_text, "user_helped", "help_agent", True):
        await update.message.reply_text(f"✅ Спасибо! 💾 Сохранено в GitHub\n📝 {help_text}")
    else:
        await update.message.reply_text(f"✅ Спасибо!\n📝 {help_text}\n⚠️ GitHub не настроен")

async def reset_memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await request_permission(update, "delete_memory", "Очистка всей памяти агента", {})

async def dialog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['dialog_active'] = True
    context.user_data['dialog_history'] = []
    await update.message.reply_text("🗣️ **Диалог начат!**\nПросто пишите мне.\n/end_dialog - закончить")

async def end_dialog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['dialog_active'] = False
    context.user_data['dialog_history'] = []
    await update.message.reply_text("👋 **Диалог завершен!**")

async def clear_dialog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'dialog_history' in context.user_data:
        context.user_data['dialog_history'] = []
        await update.message.reply_text("🧹 История диалога очищена!")
    else:
        await update.message.reply_text("📭 История пуста")

async def agent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not AGNES_API_KEY:
        await update.message.reply_text("❌ Agnes AI не настроен.")
        return
    if not context.args:
        await update.message.reply_text("🤖 /agent <запрос>\nПример: /agent перейди на ютуб")
        return
    user_id = update.effective_user.id
    user_request = ' '.join(context.args)
    await update.message.reply_text("🤖 Думаю...")
    try:
        learned = get_learned_actions(user_id, user_request)
        if learned:
            action = learned[0][0]
            await update.message.reply_text(f"🧠 Я знаю это! Делаю: {action}")
            if "/go" in action:
                url = action.replace("/go", "").strip()
                success, msg = await go_to_url(url)
                if success:
                    screenshot_data, _ = await take_screenshot()
                    if screenshot_data:
                        screenshot_bytes = base64.b64decode(screenshot_data)
                        await update.message.reply_photo(screenshot_bytes, caption=f"📸 {msg}")
                    await update.message.reply_text(f"✅ {msg}")
            elif "/screen" in action:
                screenshot_data, error = await take_screenshot()
                if screenshot_data:
                    screenshot_bytes = base64.b64decode(screenshot_data)
                    await update.message.reply_photo(screenshot_bytes, caption="📸 Скриншот")
            return
        page_info = await get_page_info()
        agnes_response, error = call_agnes_agent(user_request, page_info)
        if error:
            await update.message.reply_text(f"🤔 Не знаю. Помогите: /help_agent\nИли /library")
            return
        await update.message.reply_text(f"🤖 {agnes_response}")
        if any(word in user_request.lower() for word in ['перейди', 'зайди', 'открой', 'google', 'vk', 'youtube']):
            url_match = re.search(r'(https?://[^\s]+|google\.com|vk\.com|youtube\.com|yandex\.ru)', user_request)
            if url_match:
                url = url_match.group(0)
                if not url.startswith('http'):
                    url = 'https://' + url
                success, msg = await go_to_url(url)
                if success:
                    screenshot_data, _ = await take_screenshot()
                    if screenshot_data:
                        screenshot_bytes = base64.b64decode(screenshot_data)
                        await update.message.reply_photo(screenshot_bytes, caption=f"📸 {msg}")
                    await update.message.reply_text(f"✅ {msg}")
        elif any(word in user_request.lower() for word in ['скрин', 'screenshot']):
            screenshot_data, error = await take_screenshot()
            if screenshot_data:
                screenshot_bytes = base64.b64decode(screenshot_data)
                await update.message.reply_photo(screenshot_bytes, caption="📸 Скриншот")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# --- ЭКСПЕРИМЕНТЫ ---
async def agent_experiment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not AGNES_API_KEY:
        await update.message.reply_text("❌ Agnes AI не настроен.")
        return
    if not context.args:
        await update.message.reply_text("🧪 /experiment <цель>\nПример: /experiment создать логотип")
        return
    user_id = update.effective_user.id
    goal = ' '.join(context.args)
    await update.message.reply_text(f"🧪 Начинаю эксперимент!\n🎯 Цель: {goal}")
    attempts = 0
    best_result = ""
    best_prompt = ""
    feedback = ""
    while attempts < 5:
        attempts += 1
        if attempts == 1:
            current_prompt = goal
        else:
            current_prompt, error = optimize_prompt(current_prompt, f"Цель: {goal}", feedback)
            if error:
                await update.message.reply_text(f"❌ Ошибка: {error}")
                break
        await update.message.reply_text(f"🔄 Попытка {attempts}:\n📝 {current_prompt[:100]}...")
        try:
            headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
            payload = {"model": "agnes-2.0-flash", "messages": [{"role": "system", "content": "Ты - креативный помощник."}, {"role": "user", "content": current_prompt}], "max_tokens": 1000}
            response = requests.post(AGNES_API_URL, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            current_result = result['choices'][0]['message']['content']
            if not best_result or len(current_result) > len(best_result):
                best_result = current_result
                best_prompt = current_prompt
            await update.message.reply_text(f"📊 Результат {attempts}: {current_result[:300]}...")
            if attempts >= 3:
                break
            feedback = f"Улучшить: {goal}. Текущий: {current_result[:100]}..."
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
            break
    save_experiment_memory(user_id, goal, attempts, best_result, "completed")
    if best_result:
        await update.message.reply_text(f"🏆 Эксперимент завершен!\n🎯 {goal}\n🔄 {attempts} попыток\n✨ {best_result}")
    else:
        await update.message.reply_text("❌ Эксперимент не дал результатов.")

def optimize_prompt(original_prompt, context, feedback=""):
    if not AGNES_API_KEY:
        return original_prompt, "AGNES_API_KEY не установлен"
    try:
        system_prompt = "Ты - эксперт по оптимизации промтов. Улучши промт, учитывая контекст и обратную связь."
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Промт: {original_prompt}"}, {"role": "user", "content": f"Контекст: {context}"}]
        if feedback:
            messages.append({"role": "user", "content": f"Обратная связь: {feedback}"})
        messages.append({"role": "user", "content": "Предложи улучшенную версию"})
        headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "agnes-2.0-flash", "messages": messages, "max_tokens": 500}
        response = requests.post(AGNES_API_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
        optimized = result['choices'][0]['message']['content']
        if ":" in optimized:
            optimized = optimized.split(":")[-1].strip()
        if "```" in optimized:
            optimized = optimized.replace("```", "").strip()
        return optimized, None
    except Exception as e:
        return original_prompt, str(e)

async def experiments_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    experiments = get_experiments_memory(user_id)
    if not experiments:
        await update.message.reply_text("📭 Экспериментов нет.")
        return
    response = "🧪 **История экспериментов:**\n\n"
    for exp in experiments[-5:]:
        response += f"🎯 {exp['goal'][:50]}...\n🔄 {exp['attempts']} попыток\n📊 {exp['status']}\n\n"
    await update.message.reply_text(response)

async def stop_experiment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛑 Эксперимент остановлен.")

# --- ОБРАБОТЧИК СООБЩЕНИЙ ---
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        context.user_data['last_image'] = bytes(photo_bytes)
        await update.message.reply_text("📸 Фото сохранено!\n/bg <описание>")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text
    if user_message.startswith('/'):
        return
    if 'dialog_active' not in context.user_data or not context.user_data['dialog_active']:
        await update.message.reply_text("👋 Используйте /dialog для начала диалога")
        return
    # Обучение в диалоге
    learn_patterns = ['запомни', 'запомни что', 'научись', 'когда я говорю', 'делай так']
    if any(pattern in user_message.lower() for pattern in learn_patterns):
        match = re.search(r'когда я говорю\s+"?([^"]+)"?\s+делай\s+"?([^"]+)"?', user_message.lower())
        if match:
            command, action = match.group(1).strip(), match.group(2).strip()
            if save_learning(user_id, command, action, "dialog_learning", True):
                await update.message.reply_text(f"✅ Запомнил! 💾\n{command} -> {action}")
            return
        match = re.search(r'"([^"]+)"\s*[->=]\s*"?([^"]+)"?', user_message)
        if match:
            command, action = match.group(1).strip(), match.group(2).strip()
            if save_learning(user_id, command, action, "dialog_learning", True):
                await update.message.reply_text(f"✅ Запомнил! 💾\n{command} -> {action}")
            return
    # Проверка выученных команд
    learned = get_learned_actions(user_id, user_message)
    if learned:
        action = learned[0][0]
        await update.message.reply_text(f"🧠 Знаю! Делаю: {action}")
        if "/go" in action:
            url = action.replace("/go", "").strip()
            success, msg = await go_to_url(url)
            if success:
                screenshot_data, _ = await take_screenshot()
                if screenshot_data:
                    screenshot_bytes = base64.b64decode(screenshot_data)
                    await update.message.reply_photo(screenshot_bytes, caption=f"📸 {msg}")
                await update.message.reply_text(f"✅ {msg}")
        elif "/screen" in action:
            screenshot_data, error = await take_screenshot()
            if screenshot_data:
                screenshot_bytes = base64.b64decode(screenshot_data)
                await update.message.reply_photo(screenshot_bytes, caption="📸 Скриншот")
        return
    # Обычный диалог
    await update.message.reply_text("🤖 Думаю...")
    try:
        if 'dialog_history' not in context.user_data:
            context.user_data['dialog_history'] = []
        context.user_data['dialog_history'].append({"role": "user", "content": user_message})
        page_info = await get_page_info()
        system_prompt = get_agent_capabilities()
        messages = [{"role": "system", "content": system_prompt}]
        if page_info['url']:
            messages.append({"role": "user", "content": f"Текущая страница: {page_info['url']}\nЗаголовок: {page_info['title']}"})
        history = context.user_data['dialog_history'][-10:]
        for msg in history:
            messages.append(msg)
        messages.append({"role": "user", "content": user_message})
        headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "agnes-2.0-flash", "messages": messages, "max_tokens": 1000}
        response = requests.post(AGNES_API_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
        agent_reply = result['choices'][0]['message']['content']
        context.user_data['dialog_history'].append({"role": "assistant", "content": agent_reply})
        await update.message.reply_text(f"🤖 {agent_reply}")
        # Автоматическое выполнение действий
        if any(word in user_message.lower() for word in ['перейди', 'зайди', 'открой', 'google', 'vk', 'youtube']):
            url_match = re.search(r'(https?://[^\s]+|google\.com|vk\.com|youtube\.com|yandex\.ru)', user_message)
            if url_match:
                url = url_match.group(0)
                if not url.startswith('http'):
                    url = 'https://' + url
                success, msg = await go_to_url(url)
                if success:
                    screenshot_data, _ = await take_screenshot()
                    if screenshot_data:
                        screenshot_bytes = base64.b64decode(screenshot_data)
                        await update.message.reply_photo(screenshot_bytes, caption=f"📸 {msg}")
                    await update.message.reply_text(f"✅ {msg}")
        elif any(word in user_message.lower() for word in ['скрин', 'screenshot']):
            screenshot_data, error = await take_screenshot()
            if screenshot_data:
                screenshot_bytes = base64.b64decode(screenshot_data)
                await update.message.reply_photo(screenshot_bytes, caption="📸 Скриншот")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# --- БИБЛИОТЕКА РЕСУРСОВ ---
RESOURCE_LIBRARY = {
    "github": {
        "name": "GitHub",
        "resources": {
            "ai_agents": {"name": "AI Agents для начинающих", "url": "https://github.com/microsoft/ai-agents-for-beginners", "description": "Курс от Microsoft"},
            "pydoll": {"name": "Pydoll", "url": "https://github.com/pydoll/pydoll", "description": "Управление браузером"},
            "langgraph": {"name": "LangGraph", "url": "https://github.com/langchain-ai/langgraph", "description": "Агентные системы"}
        }
    },
    "docs": {
        "name": "Документация",
        "resources": {
            "agnes_api": {"name": "Agnes AI API", "url": "https://docs.agnes-ai.com", "description": "Документация Agnes AI"},
            "telegram_bot": {"name": "Python Telegram Bot", "url": "https://docs.python-telegram-bot.org", "description": "Документация"}
        }
    }
}

async def library_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = "📚 **Библиотека ресурсов**\n\n"
    for cat_key, cat in RESOURCE_LIBRARY.items():
        response += f"📁 **{cat['name']}**\n"
        for res_key, res in cat['resources'].items():
            response += f"• {res['name']}\n  {res['description']}\n  🔗 {res['url']}\n\n"
    response += "\n💡 /library <категория>\n/library find <текст>"
    await update.message.reply_text(response)

async def library_category_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await library_command(update, context)
        return
    category_key = context.args[0].lower()
    if category_key == "find":
        search_text = ' '.join(context.args[1:]).lower()
        if not search_text:
            await update.message.reply_text("❌ Укажите текст поиска")
            return
        results = []
        for cat_key, cat in RESOURCE_LIBRARY.items():
            for res_key, res in cat['resources'].items():
                if search_text in res['name'].lower() or search_text in res['description'].lower():
                    results.append((cat['name'], res))
        if results:
            response = f"🔍 **Результаты: '{search_text}'**\n\n"
            for cat_name, res in results:
                response += f"📁 {cat_name}\n• {res['name']}\n  {res['description']}\n  🔗 {res['url']}\n\n"
            await update.message.reply_text(response)
        else:
            await update.message.reply_text(f"❌ Ничего не найдено")
        return
    if category_key not in RESOURCE_LIBRARY:
        await update.message.reply_text(f"❌ Категория не найдена. Доступны: {', '.join(RESOURCE_LIBRARY.keys())}")
        return
    cat = RESOURCE_LIBRARY[category_key]
    response = f"📁 **{cat['name']}**\n\n"
    for res_key, res in cat['resources'].items():
        response += f"• {res['name']}\n  {res['description']}\n  🔗 {res['url']}\n\n"
    await update.message.reply_text(response)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

# --- ГЛАВНАЯ ФУНКЦИЯ ---
def main():
    try:
        application = Application.builder().token(TOKEN).build()
        # Браузер
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("open_bw", open_browser_command))
        application.add_handler(CommandHandler("close_bw", close_browser_command))
        application.add_handler(CommandHandler("screen", screenshot_command))
        application.add_handler(CommandHandler("go", go_command))
        # Фотошоп
        application.add_handler(CommandHandler("bg", bg_command))
        application.add_handler(CommandHandler("clear", clear_command))
        # Эксперименты
        application.add_handler(CommandHandler("experiment", agent_experiment_command))
        application.add_handler(CommandHandler("experiments", experiments_history_command))
        application.add_handler(CommandHandler("stop_experiment", stop_experiment_command))
        # Ресурсы
        application.add_handler(CommandHandler("library", library_command))
        application.add_handler(CommandHandler("library", library_category_command))
        # Агент
        application.add_handler(CommandHandler("agent", agent_command))
        application.add_handler(CommandHandler("learn", learn_command))
        application.add_handler(CommandHandler("knowledge", knowledge_command))
        application.add_handler(CommandHandler("help_agent", help_agent_command))
        application.add_handler(CommandHandler("reset_memory", reset_memory_command))
        application.add_handler(CommandHandler("capabilities", capabilities_command))
        # Диалог
        application.add_handler(CommandHandler("dialog", dialog_command))
        application.add_handler(CommandHandler("end_dialog", end_dialog_command))
        application.add_handler(CommandHandler("clear_dialog", clear_dialog_command))
        # Старт
        application.add_handler(CommandHandler("start", start))
        # Обработчики
        application.add_handler(CallbackQueryHandler(permit_callback))
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_error_handler(error_handler)
        logger.info("🚀 Бот запущен!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise

if __name__ == "__main__":
    main()