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
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
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

CHROME_PATH = "/usr/bin/google-chrome"
AGNES_API_URL = "https://apihub.agnes-ai.com/v1/chat/completions"
AGNES_IMAGE_URL = "https://apihub.agnes-ai.com/v1/images/generations"

# --- БИБЛИОТЕКА ПОЛЕЗНЫХ РЕСУРСОВ ---
RESOURCE_LIBRARY = {
    "github": {
        "name": "GitHub - Репозитории с кодом",
        "description": "Платформа для хостинга IT-проектов и совместной разработки",
        "resources": {
            "ai_agents": {
                "name": "AI Agents для начинающих",
                "url": "https://github.com/microsoft/ai-agents-for-beginners",
                "description": "Официальный курс от Microsoft с 12 уроками по созданию AI-агентов"
            },
            "pydoll": {
                "name": "Pydoll - документация",
                "url": "https://github.com/pydoll/pydoll",
                "description": "Библиотека для управления браузером с защитой от блокировок"
            },
            "langgraph": {
                "name": "LangGraph - агентные системы",
                "url": "https://github.com/langchain-ai/langgraph",
                "description": "Фреймворк для создания агентов с графовой архитектурой"
            },
            "openai_agents": {
                "name": "OpenAI Agents SDK",
                "url": "https://github.com/openai/openai-agents-python",
                "description": "Официальный SDK от OpenAI для создания агентов"
            },
            "agnes_skills": {
                "name": "Agnes AI Skills",
                "url": "https://github.com/Agnes-AI/agnes-ai",
                "description": "Набор скиллов для работы с Agnes AI API"
            }
        }
    },
    "docs": {
        "name": "Документация и туториалы",
        "description": "Официальная документация и руководства",
        "resources": {
            "agnes_api": {
                "name": "Agnes AI API Docs",
                "url": "https://docs.agnes-ai.com",
                "description": "Полная документация по API Agnes AI"
            },
            "python_telegram_bot": {
                "name": "Python Telegram Bot",
                "url": "https://docs.python-telegram-bot.org",
                "description": "Документация по библиотеке python-telegram-bot"
            },
            "pydoll_docs": {
                "name": "Pydoll Documentation",
                "url": "https://pydoll.readthedocs.io",
                "description": "Документация по Pydoll с примерами"
            }
        }
    },
    "learning": {
        "name": "Образовательные ресурсы",
        "description": "Курсы, статьи и учебные материалы",
        "resources": {
            "ai_camp": {
                "name": "AI Agent Camp",
                "url": "https://github.com/ai-agent-camp",
                "description": "Готовые команды и скиллы для AI-агентов"
            },
            "deeplearning": {
                "name": "DeepLearning.AI",
                "url": "https://www.deeplearning.ai",
                "description": "Курсы по AI от Эндрю Ынга"
            },
            "fastapi": {
                "name": "FastAPI - создание API",
                "url": "https://fastapi.tiangolo.com",
                "description": "Современный фреймворк для создания API на Python"
            }
        }
    },
    "tools": {
        "name": "Инструменты для разработки",
        "description": "Полезные инструменты и библиотеки",
        "resources": {
            "telegram_bot": {
                "name": "Telegram Bot API",
                "url": "https://core.telegram.org/bots/api",
                "description": "Официальная документация Telegram Bot API"
            },
            "requests": {
                "name": "Requests - HTTP для Python",
                "url": "https://docs.python-requests.org",
                "description": "Библиотека для работы с HTTP-запросами"
            },
            "pillow": {
                "name": "Pillow - работа с изображениями",
                "url": "https://pillow.readthedocs.io",
                "description": "Библиотека для обработки изображений"
            }
        }
    },
    "community": {
        "name": "Сообщества и форумы",
        "description": "Места для общения и получения помощи",
        "resources": {
            "stackoverflow": {
                "name": "Stack Overflow",
                "url": "https://stackoverflow.com/questions/tagged/python",
                "description": "Вопросы и ответы по Python"
            },
            "telegram_chat": {
                "name": "Telegram Python Chat",
                "url": "https://t.me/ru_python",
                "description": "Русскоязычный чат по Python в Telegram"
            },
            "reddit": {
                "name": "Reddit r/learnpython",
                "url": "https://www.reddit.com/r/learnpython/",
                "description": "Сообщество для изучения Python"
            }
        }
    }
}

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('agent_memory.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agent_learning (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            command TEXT,
            action TEXT,
            context TEXT,
            success INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agent_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            question TEXT,
            answer TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agent_help_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task TEXT,
            reason TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agent_prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            original_prompt TEXT,
            optimized_prompt TEXT,
            result TEXT,
            success INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agent_experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            goal TEXT,
            attempts INTEGER,
            best_result TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agent_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            total_commands INTEGER DEFAULT 0,
            total_learned INTEGER DEFAULT 0,
            total_experiments INTEGER DEFAULT 0,
            success_rate REAL DEFAULT 0,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# --- ФУНКЦИИ СТАТИСТИКИ ---
def get_agent_stats(user_id):
    conn = sqlite3.connect('agent_memory.db')
    cursor = conn.cursor()
    
    # Получаем общую статистику
    cursor.execute(
        'SELECT total_commands, total_learned, total_experiments, success_rate FROM agent_stats WHERE user_id = ?',
        (user_id,)
    )
    stats = cursor.fetchone()
    
    if not stats:
        stats = (0, 0, 0, 0.0)
    
    # Получаем количество выученных команд
    cursor.execute(
        'SELECT COUNT(*) FROM agent_learning WHERE user_id = ? AND success = 1',
        (user_id,)
    )
    learned_count = cursor.fetchone()[0]
    
    # Получаем количество экспериментов
    cursor.execute(
        'SELECT COUNT(*) FROM agent_experiments WHERE user_id = ? AND status = "completed"',
        (user_id,)
    )
    experiments_count = cursor.fetchone()[0]
    
    # Получаем последние действия
    cursor.execute(
        'SELECT command, action, created_at FROM agent_learning WHERE user_id = ? ORDER BY created_at DESC LIMIT 3',
        (user_id,)
    )
    recent_actions = cursor.fetchall()
    
    conn.close()
    
    return {
        'total_commands': stats[0],
        'total_learned': stats[1],
        'total_experiments': stats[2],
        'success_rate': stats[3],
        'learned_count': learned_count,
        'experiments_count': experiments_count,
        'recent_actions': recent_actions
    }

def update_agent_stats(user_id, command_type, success=True):
    conn = sqlite3.connect('agent_memory.db')
    cursor = conn.cursor()
    
    cursor.execute(
        'SELECT total_commands, total_learned, total_experiments, success_rate FROM agent_stats WHERE user_id = ?',
        (user_id,)
    )
    stats = cursor.fetchone()
    
    if stats:
        total_commands, total_learned, total_experiments, success_rate = stats
        total_commands += 1
        
        if command_type == 'learn':
            total_learned += 1
        elif command_type == 'experiment':
            total_experiments += 1
        
        # Обновляем процент успеха
        if success:
            success_rate = (success_rate * (total_commands - 1) + 1) / total_commands
        else:
            success_rate = (success_rate * (total_commands - 1)) / total_commands
        
        cursor.execute(
            'UPDATE agent_stats SET total_commands = ?, total_learned = ?, total_experiments = ?, success_rate = ?, last_active = CURRENT_TIMESTAMP WHERE user_id = ?',
            (total_commands, total_learned, total_experiments, success_rate, user_id)
        )
    else:
        cursor.execute(
            'INSERT INTO agent_stats (user_id, total_commands, total_learned, total_experiments, success_rate) VALUES (?, ?, ?, ?, ?)',
            (user_id, 1, 1 if command_type == 'learn' else 0, 1 if command_type == 'experiment' else 0, 1.0)
        )
    
    conn.commit()
    conn.close()

# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ---
browser_instance = None
tab_instance = None
current_url = None
page_title = None
page_content = None
start_time = datetime.now()

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
        page_content = await tab_instance.get_text()
        
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
    return {
        'url': current_url,
        'title': page_title,
        'content': page_content[:1000] if page_content else None
    }

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С AGNES ---
def call_agnes_agent(prompt: str, context: dict = None, learning_context: str = None):
    if not AGNES_API_KEY:
        return None, "AGNES_API_KEY не установлен"
    
    try:
        system_prompt = """Ты - AI агент, управляющий браузером. У тебя есть доступ к библиотеке полезных ресурсов.
        
        Если ты не знаешь, как решить проблему - обратись к библиотеке ресурсов.
        
        Ты можешь:
        1. Переходить по ссылкам
        2. Делать скриншоты
        3. Получать информацию со страницы
        4. Анализировать контент страницы
        5. Искать информацию в библиотеке ресурсов
        6. Предлагать пользователю полезные ссылки
        
        Если пользователь спрашивает о чем-то, что связано с программированием, AI, Python - предложи соответствующие ресурсы из библиотеки."""
        
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        if learning_context:
            messages.append({"role": "system", "content": f"Контекст: {learning_context}"})
        
        if context:
            context_str = f"\nТекущее состояние:\nURL: {context.get('url', 'Неизвестно')}\nЗаголовок: {context.get('title', 'Неизвестно')}"
            messages.append({"role": "user", "content": context_str})
        
        messages.append({"role": "user", "content": prompt})
        
        headers = {
            "Authorization": f"Bearer {AGNES_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "agnes-2.0-flash",
            "messages": messages,
            "max_tokens": 1000
        }
        
        response = requests.post(AGNES_API_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        return result['choices'][0]['message']['content'], None
        
    except Exception as e:
        logger.error(f"Ошибка Agnes: {e}")
        return None, str(e)

# --- КОМАНДА /STATUS (ОБНОВЛЕННАЯ) ---
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статус браузера и показатели агента"""
    user_id = update.effective_user.id
    
    # Статус браузера
    browser_status = "🟢 Включен" if browser_instance is not None and tab_instance is not None else "🔴 Выключен"
    
    # Статистика агента
    stats = get_agent_stats(user_id)
    
    # Информация о системе
    uptime = datetime.now() - start_time
    uptime_str = str(uptime).split('.')[0]
    
    # Память
    memory = psutil.virtual_memory()
    memory_used = memory.used / (1024**3)  # GB
    memory_total = memory.total / (1024**3)  # GB
    
    # CPU
    cpu_percent = psutil.cpu_percent(interval=0.5)
    
    # Проверка API ключей
    agnes_status = "✅ Настроен" if AGNES_API_KEY else "❌ Не настроен"
    
    # Создаем ответ
    response = (
        "📊 **Статус системы**\n\n"
        
        "🖥️ **Браузер:**\n"
        f"  • Статус: {browser_status}\n"
        f"  • Путь: {CHROME_PATH}\n"
        f"  • Headless: ✅\n\n"
        
        "🤖 **Агент:**\n"
        f"  • Agnes AI: {agnes_status}\n"
        f"  • Команд выполнено: {stats['total_commands']}\n"
        f"  • Выучено команд: {stats['learned_count']}\n"
        f"  • Экспериментов: {stats['experiments_count']}\n"
        f"  • Успешность: {stats['success_rate']*100:.1f}%\n\n"
        
        "🧠 **Память агента:**\n"
        f"  • Всего знаний: {stats['total_learned']}\n"
        f"  • Успешных действий: {len([a for a in stats['recent_actions'] if a])}\n\n"
        
        "⚙️ **Система:**\n"
        f"  • Время работы: {uptime_str}\n"
        f"  • CPU: {cpu_percent}%\n"
        f"  • Память: {memory_used:.1f}GB / {memory_total:.1f}GB ({memory.percent}%)\n"
        f"  • OS: {platform.system()} {platform.release()}\n\n"
        
        "📚 **Библиотека:**\n"
        f"  • Ресурсов: {sum(len(cat['resources']) for cat in RESOURCE_LIBRARY.values())}\n"
        f"  • Категорий: {len(RESOURCE_LIBRARY)}\n\n"
    )
    
    # Добавляем последние действия
    if stats['recent_actions']:
        response += "🔄 **Последние действия:**\n"
        for cmd, action, date in stats['recent_actions']:
            date_str = date[:16] if date else "недавно"
            response += f"  • {cmd} -> {action[:30]}... ({date_str})\n"
    
    # Добавляем рекомендации
    if stats['total_commands'] < 5:
        response += "\n💡 **Совет:** Используйте /learn, чтобы научить меня новым командам!"
    elif stats['learned_count'] < 3:
        response += "\n💡 **Совет:** Я еще мало знаю. Научите меня чему-нибудь через /learn!"
    
    if not AGNES_API_KEY:
        response += "\n⚠️ **Внимание:** Agnes AI не настроен! Некоторые функции недоступны."
    
    await update.message.reply_text(response)

# --- ОСТАЛЬНЫЕ КОМАНДЫ ---
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
        "📚 **Ресурсы:**\n"
        "/library - Библиотека ресурсов\n"
        "/library <категория> - Ресурсы по категории\n"
        "/library find <текст> - Поиск ресурсов\n"
        "🤖 **Агент:**\n"
        "/agent <запрос> - Управление через AI\n"
        "/learn <команда -> действие> - Научить агента\n"
        "/knowledge - Что умеет агент\n"
        "/help_agent <описание> - Помочь агенту"
    )

# --- ОСТАЛЬНЫЕ КОМАНДЫ (без изменений) ---
async def open_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    success = await open_browser()
    if success:
        await update.message.reply_text("🌐 Браузер открыт ✅")
    else:
        await update.message.reply_text("❌ Не удалось открыть браузер")

async def close_browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    success = await close_browser()
    if success:
        await update.message.reply_text("❌ Браузер закрыт ✅")
    else:
        await update.message.reply_text("❌ Не удалось закрыть браузер")

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
    if success:
        await update.message.reply_text(f"✅ {msg}")
    else:
        await update.message.reply_text(f"❌ {msg}")

# --- ЗАМЕНА ФОНА ---
def replace_background(image_data, new_background_prompt: str):
    if not AGNES_API_KEY:
        return None, "AGNES_API_KEY не установлен!"
    
    try:
        img_b64 = base64.b64encode(image_data).decode('utf-8')
        data_uri = f"data:image/jpeg;base64,{img_b64}"
        
        headers = {
            "Authorization": f"Bearer {AGNES_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "agnes-image-2.0-flash",
            "prompt": f"Replace the background with: {new_background_prompt}. Keep the main subject unchanged.",
            "size": "1024x1024",
            "extra_body": {
                "image": [data_uri],
                "response_format": "url"
            }
        }
        
        response = requests.post(AGNES_IMAGE_URL, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        return result['data'][0]['url'], None
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return None, str(e)

async def bg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not AGNES_API_KEY:
        await update.message.reply_text("❌ Agnes AI не настроен.")
        return
    
    if 'last_image' not in context.user_data:
        await update.message.reply_text("📸 Сначала загрузите картинку!")
        return
    
    if not context.args:
        await update.message.reply_text("✏️ Напишите описание нового фона.\nПример: /bg beach")
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
        await update.message.reply_text(
            "📚 Как обучить агента:\n"
            "/learn <команда> -> <действие>\n\n"
            "Примеры:\n"
            "/learn зайди на ютуб -> /go youtube.com\n"
            "/learn сделай скрин -> /screen"
        )
        return
    
    user_id = update.effective_user.id
    text = ' '.join(context.args)
    
    if '->' in text:
        parts = text.split('->')
        command = parts[0].strip()
        action = parts[1].strip()
        
        save_learning(user_id, command, action, "user_taught", True)
        update_agent_stats(user_id, 'learn', True)
        
        await update.message.reply_text(
            f"✅ Я запомнил!\n"
            f"Команда: {command}\n"
            f"Действие: {action}"
        )
    else:
        await update.message.reply_text("❌ Неправильный формат. Используйте: /learn команда -> действие")

async def knowledge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('agent_memory.db')
    cursor = conn.cursor()
    
    cursor.execute(
        'SELECT command, action FROM agent_learning WHERE user_id = ? AND success = 1 ORDER BY created_at DESC LIMIT 10',
        (user_id,)
    )
    learnings = cursor.fetchall()
    
    cursor.execute(
        'SELECT goal, best_result FROM agent_experiments WHERE user_id = ? AND status = "completed" ORDER BY created_at DESC LIMIT 3',
        (user_id,)
    )
    experiments = cursor.fetchall()
    
    conn.close()
    
    response = "🧠 Что я умею:\n\n"
    
    if learnings:
        response += "📚 Выученные команды:\n"
        for cmd, action in learnings:
            response += f"• {cmd} -> {action}\n"
    
    if experiments:
        response += "\n🧪 Успешные эксперименты:\n"
        for goal, result in experiments:
            response += f"• {goal[:50]}...\n"
    
    if not learnings and not experiments:
        response = "📭 Я пока ничего не выучил. Научи меня чему-нибудь!"
    
    await update.message.reply_text(response)

async def help_agent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🤝 Помогите агенту:\n"
            "/help_agent <описание задачи>\n\n"
            "Пример: /help_agent я нажал кнопку Войти, теперь нужно ввести логин"
        )
        return
    
    user_id = update.effective_user.id
    help_text = ' '.join(context.args)
    
    save_learning(user_id, help_text, "user_helped", "help_agent", True)
    update_agent_stats(user_id, 'learn', True)
    
    await update.message.reply_text(
        f"✅ Спасибо за помощь! Я запомнил.\n"
        f"📝 Вы сказали: {help_text}"
    )

async def agent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not AGNES_API_KEY:
        await update.message.reply_text("❌ Agnes AI не настроен.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "🤖 Команды агента:\n"
            "/agent <запрос> - Управление через AI\n"
            "/experiment <цель> - Эксперимент с промтами\n"
            "/learn <команда -> действие> - Научить агента\n"
            "/knowledge - Что умеет агент\n"
            "/library - Библиотека ресурсов\n"
            "/help_agent <описание> - Помочь агенту"
        )
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
                        await update.message.reply_photo(
                            screenshot_bytes,
                            caption=f"📸 {msg}"
                        )
                    await update.message.reply_text(f"✅ {msg}")
                    update_agent_stats(user_id, 'command', True)
                else:
                    await update.message.reply_text(f"❌ {msg}")
                    update_agent_stats(user_id, 'command', False)
            elif "/screen" in action:
                screenshot_data, error = await take_screenshot()
                if screenshot_data:
                    screenshot_bytes = base64.b64decode(screenshot_data)
                    await update.message.reply_photo(screenshot_bytes, caption="📸 Скриншот")
                    update_agent_stats(user_id, 'command', True)
                else:
                    await update.message.reply_text(f"❌ {error}")
                    update_agent_stats(user_id, 'command', False)
            else:
                await update.message.reply_text(f"⚠️ Не знаю как выполнить: {action}")
            return
        
        page_info = await get_page_info()
        agnes_response, error = call_agnes_agent(
            f"Пользователь просит: {user_request}\nЧто нужно сделать в браузере?",
            page_info
        )
        
        if error:
            await update.message.reply_text(
                f"🤔 Я не знаю, как выполнить ваш запрос.\n"
                f"Помогите мне: /help_agent <описание>\n"
                f"Или посмотрите в библиотеке ресурсов: /library"
            )
            update_agent_stats(user_id, 'command', False)
            return
        
        await update.message.reply_text(f"🤖 Агент:\n{agnes_response}")
        
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
                        await update.message.reply_photo(
                            screenshot_bytes,
                            caption=f"📸 {msg}"
                        )
                    await update.message.reply_text(f"✅ {msg}")
                    update_agent_stats(user_id, 'command', True)
                else:
                    await update.message.reply_text(f"❌ {msg}")
                    update_agent_stats(user_id, 'command', False)
        
        elif any(word in user_request.lower() for word in ['скрин', 'screenshot']):
            screenshot_data, error = await take_screenshot()
            if screenshot_data:
                screenshot_bytes = base64.b64decode(screenshot_data)
                await update.message.reply_photo(screenshot_bytes, caption="📸 Скриншот")
                update_agent_stats(user_id, 'command', True)
            else:
                await update.message.reply_text(f"❌ {error}")
                update_agent_stats(user_id, 'command', False)
        
    except Exception as e:
        logger.error(f"Ошибка агента: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        update_agent_stats(user_id, 'command', False)

# --- ЭКСПЕРИМЕНТЫ ---
async def agent_experiment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not AGNES_API_KEY:
        await update.message.reply_text("❌ Agnes AI не настроен.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "🧪 Агент-экспериментатор:\n"
            "/experiment <цель>\n\n"
            "Примеры:\n"
            "/experiment создать логотип для бота\n"
            "/experiment написать пост для Instagram"
        )
        return
    
    user_id = update.effective_user.id
    goal = ' '.join(context.args)
    
    await update.message.reply_text(
        f"🧪 Начинаю эксперимент!\n"
        f"🎯 Цель: {goal}\n"
        f"⏳ Это может занять несколько попыток..."
    )
    
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
                await update.message.reply_text(f"❌ Ошибка оптимизации: {error}")
                break
        
        await update.message.reply_text(f"🔄 Попытка {attempts}:\n📝 Промт: {current_prompt[:100]}...")
        
        try:
            headers = {
                "Authorization": f"Bearer {AGNES_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "agnes-2.0-flash",
                "messages": [
                    {"role": "system", "content": "Ты - креативный помощник. Создай качественный результат."},
                    {"role": "user", "content": current_prompt}
                ],
                "max_tokens": 1000
            }
            
            response = requests.post(AGNES_API_URL, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            current_result = result['choices'][0]['message']['content']
            
            if not best_result or len(current_result) > len(best_result):
                best_result = current_result
                best_prompt = current_prompt
                save_prompt_optimization(user_id, goal, current_prompt, current_result, True)
            
            await update.message.reply_text(
                f"📊 Результат попытки {attempts}:\n"
                f"{current_result[:300]}...\n"
            )
            
            if attempts >= 3:
                break
                
            feedback = f"Пользователь хочет улучшить: {goal}. Текущий результат: {current_result[:100]}..."
            
        except Exception as e:
            logger.error(f"Ошибка эксперимента: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
            break
    
    save_experiment(user_id, goal, attempts, best_result, "completed")
    update_agent_stats(user_id, 'experiment', True)
    
    if best_result:
        await update.message.reply_text(
            f"🏆 Эксперимент завершен!\n"
            f"🎯 Цель: {goal}\n"
            f"🔄 Попыток: {attempts}\n"
            f"📝 Лучший промт: {best_prompt}\n\n"
            f"✨ Результат:\n{best_result}"
        )
    else:
        await update.message.reply_text(
            f"❌ Эксперимент не дал результатов.\n"
            f"Попробуйте изменить цель."
        )

def optimize_prompt(original_prompt, context, feedback=""):
    if not AGNES_API_KEY:
        return original_prompt, "AGNES_API_KEY не установлен"
    
    try:
        system_prompt = """Ты - эксперт по оптимизации промтов для AI.
        Улучши промт, чтобы получить лучший результат.
        Учитывай контекст и обратную связь.
        
        Правила оптимизации:
        1. Добавляй больше деталей
        2. Уточняй стиль и качество
        3. Добавляй ограничения и требования
        4. Делай промт более конкретным"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Оригинальный промт: {original_prompt}"},
            {"role": "user", "content": f"Контекст: {context}"}
        ]
        
        if feedback:
            messages.append({"role": "user", "content": f"Обратная связь: {feedback}"})
        
        messages.append({"role": "user", "content": "Предложи улучшенную версию промта"})
        
        headers = {
            "Authorization": f"Bearer {AGNES_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "agnes-2.0-flash",
            "messages": messages,
            "max_tokens": 500
        }
        
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
        logger.error(f"Ошибка оптимизации: {e}")
        return original_prompt, str(e)

# --- БИБЛИОТЕКА РЕСУРСОВ ---
async def library_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = "📚 **Библиотека полезных ресурсов**\n\n"
    
    for category_key, category in RESOURCE_LIBRARY.items():
        response += f"📁 **{category['name']}**\n"
        response += f"_{category['description']}_\n\n"
        
        for resource_key, resource in category['resources'].items():
            response += f"• **{resource['name']}**\n"
            response += f"  {resource['description']}\n"
            response += f"  🔗 {resource['url']}\n\n"
        
        response += "---\n\n"
    
    response += "💡 **Как использовать:**\n"
    response += "/library - Показать все ресурсы\n"
    response += "/library <категория> - Ресурсы по категории\n"
    response += "/library find <текст> - Найти ресурс\n\n"
    response += "📂 Категории: github, docs, learning, tools, community"
    
    await update.message.reply_text(response)

async def library_category_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await library_command(update, context)
        return
    
    category_key = context.args[0].lower()
    
    if category_key == "find":
        search_text = ' '.join(context.args[1:]).lower()
        if not search_text:
            await update.message.reply_text("❌ Укажите текст для поиска.\nПример: /library find pydoll")
            return
        
        results = []
        for cat_key, cat_data in RESOURCE_LIBRARY.items():
            for res_key, res_data in cat_data['resources'].items():
                if search_text in res_data['name'].lower() or search_text in res_data['description'].lower():
                    results.append((cat_data['name'], res_data))
        
        if results:
            response = f"🔍 **Результаты поиска: '{search_text}'**\n\n"
            for category_name, resource in results:
                response += f"📁 {category_name}\n"
                response += f"• **{resource['name']}**\n"
                response += f"  {resource['description']}\n"
                response += f"  🔗 {resource['url']}\n\n"
            await update.message.reply_text(response)
        else:
            await update.message.reply_text(f"❌ Ничего не найдено по запросу '{search_text}'")
        return
    
    if category_key not in RESOURCE_LIBRARY:
        await update.message.reply_text(
            f"❌ Категория '{category_key}' не найдена.\n"
            f"Доступные категории: {', '.join(RESOURCE_LIBRARY.keys())}"
        )
        return
    
    category = RESOURCE_LIBRARY[category_key]
    response = f"📁 **{category['name']}**\n"
    response += f"_{category['description']}_\n\n"
    
    for resource_key, resource in category['resources'].items():
        response += f"• **{resource['name']}**\n"
        response += f"  {resource['description']}\n"
        response += f"  🔗 {resource['url']}\n\n"
    
    await update.message.reply_text(response)

async def experiments_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    experiments = get_experiments(user_id)
    
    if not experiments:
        await update.message.reply_text("📭 Вы пока не проводили экспериментов.")
        return
    
    response = "🧪 История экспериментов:\n\n"
    for goal, attempts, best_result, status in experiments:
        response += f"🎯 {goal[:50]}...\n"
        response += f"🔄 Попыток: {attempts}\n"
        response += f"📊 Статус: {status}\n"
        response += f"✨ Результат: {best_result[:100]}...\n\n"
    
    await update.message.reply_text(response)

async def stop_experiment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛑 Эксперимент остановлен по вашему запросу.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        context.user_data['last_image'] = bytes(photo_bytes)
        await update.message.reply_text("📸 Фото сохранено!\n/bg <описание>")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

def save_learning(user_id, command, action, context, success):
    conn = sqlite3.connect('agent_memory.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO agent_learning (user_id, command, action, context, success) VALUES (?, ?, ?, ?, ?)',
        (user_id, command, action, context, 1 if success else 0)
    )
    conn.commit()
    conn.close()

def get_learned_actions(user_id, command):
    conn = sqlite3.connect('agent_memory.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT action, context FROM agent_learning WHERE user_id = ? AND command LIKE ? AND success = 1 ORDER BY created_at DESC LIMIT 5',
        (user_id, f'%{command}%')
    )
    results = cursor.fetchall()
    conn.close()
    return results

def save_experiment(user_id, goal, attempts, best_result, status):
    conn = sqlite3.connect('agent_memory.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO agent_experiments (user_id, goal, attempts, best_result, status) VALUES (?, ?, ?, ?, ?)',
        (user_id, goal, attempts, best_result, status)
    )
    conn.commit()
    conn.close()

def get_experiments(user_id):
    conn = sqlite3.connect('agent_memory.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT goal, attempts, best_result, status FROM agent_experiments WHERE user_id = ? ORDER BY created_at DESC LIMIT 5',
        (user_id,)
    )
    results = cursor.fetchall()
    conn.close()
    return results

def save_prompt_optimization(user_id, original, optimized, result, success):
    conn = sqlite3.connect('agent_memory.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO agent_prompts (user_id, original_prompt, optimized_prompt, result, success) VALUES (?, ?, ?, ?, ?)',
        (user_id, original, optimized, result, 1 if success else 0)
    )
    conn.commit()
    conn.close()

def main():
    try:
        application = Application.builder().token(TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("open_bw", open_browser_command))
        application.add_handler(CommandHandler("close_bw", close_browser_command))
        application.add_handler(CommandHandler("screen", screenshot_command))
        application.add_handler(CommandHandler("go", go_command))
        application.add_handler(CommandHandler("bg", bg_command))
        application.add_handler(CommandHandler("clear", clear_command))
        application.add_handler(CommandHandler("agent", agent_command))
        application.add_handler(CommandHandler("learn", learn_command))
        application.add_handler(CommandHandler("knowledge", knowledge_command))
        application.add_handler(CommandHandler("help_agent", help_agent_command))
        application.add_handler(CommandHandler("experiment", agent_experiment_command))
        application.add_handler(CommandHandler("experiments", experiments_history_command))
        application.add_handler(CommandHandler("stop_experiment", stop_experiment_command))
        application.add_handler(CommandHandler("library", library_command))
        application.add_handler(CommandHandler("library", library_category_command))
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        application.add_error_handler(error_handler)

        logger.info("🚀 Бот запущен!")
        logger.info("📚 Библиотека ресурсов загружена!")
        logger.info("🧪 Агент может экспериментировать с промтами!")
        logger.info("📊 Добавлена расширенная статистика в /status!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise

if __name__ == "__main__":
    main()