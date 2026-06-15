import os
import logging
import requests
import json
import base64
import time
import re
import threading
from datetime import datetime
from flask import Flask, request
import telebot

# ===== НАСТРОЙКА ЛОГОВ =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== ФАЙЛЫ =====
AGENT_LOG_FILE = "agent_actions.log"
USER_COMMANDS_FILE = "user_commands.json"
ERROR_KNOWLEDGE_FILE = "error_knowledge.json"
BACKUP_DIR = "backups"
start_time = time.time()

os.makedirs(BACKUP_DIR, exist_ok=True)

# ===== БАЗА ЗНАНИЙ ОШИБОК =====
def load_error_knowledge():
    try:
        if os.path.exists(ERROR_KNOWLEDGE_FILE):
            with open(ERROR_KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return {}

def save_error_knowledge(knowledge):
    with open(ERROR_KNOWLEDGE_FILE, "w", encoding="utf-8") as f:
        json.dump(knowledge, f, ensure_ascii=False, indent=2)

def classify_error(error_text):
    error_patterns = {
        "syntax_error": ["SyntaxError", "invalid syntax", "EOL"],
        "import_error": ["ModuleNotFoundError", "ImportError", "No module"],
        "key_error": ["KeyError"],
        "value_error": ["ValueError"],
        "type_error": ["TypeError"],
        "attribute_error": ["AttributeError"],
        "timeout": ["timeout", "Timed out"],
        "connection": ["ConnectionError", "HTTPError"],
        "api_limit": ["429", "rate limit"],
        "missing_env": ["not set", "environment variable"],
    }
    for error_type, patterns in error_patterns.items():
        for pattern in patterns:
            if pattern.lower() in error_text.lower():
                return error_type
    return "unknown"

# ===== ЛОГИ =====
def log_agent_action(action, details=None, status="info"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {"timestamp": timestamp, "action": action, "status": status, "details": details}
    try:
        with open(AGENT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        logger.info(f"[ЛОГ] {action}: {details}")
    except:
        pass

def get_agent_logs(limit=50):
    try:
        if not os.path.exists(AGENT_LOG_FILE):
            return []
        with open(AGENT_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        logs = []
        for line in lines[-limit:]:
            try:
                logs.append(json.loads(line))
            except:
                logs.append({"raw": line.strip()})
        return logs
    except:
        return []

def clear_agent_logs():
    try:
        with open(AGENT_LOG_FILE, "w", encoding="utf-8") as f:
            f.write("")
        return True
    except:
        return False

def analyze_error_frequency():
    logs = get_agent_logs(1000)
    error_counts = {}
    for log in logs:
        if log.get("status") == "error":
            details = str(log.get("details", ""))
            error_type = classify_error(details)
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
    return error_counts

# ===== ПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ =====
def load_user_commands():
    try:
        if os.path.exists(USER_COMMANDS_FILE):
            with open(USER_COMMANDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return []

def save_user_command(cmd_name, description):
    commands = load_user_commands()
    commands = [c for c in commands if c["name"] != cmd_name]
    commands.append({"name": cmd_name, "description": description[:50]})
    with open(USER_COMMANDS_FILE, "w", encoding="utf-8") as f:
        json.dump(commands, f, ensure_ascii=False, indent=2)

def delete_user_command(cmd_name):
    commands = load_user_commands()
    commands = [c for c in commands if c["name"] != cmd_name]
    with open(USER_COMMANDS_FILE, "w", encoding="utf-8") as f:
        json.dump(commands, f, ensure_ascii=False, indent=2)

# ===== БЭКАПЫ =====
def save_backup(code, description):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"bot_backup_{timestamp}.py")
    with open(backup_file, "w", encoding="utf-8") as f:
        f.write(code)
    log_agent_action("backup_saved", f"{description}", "success")
    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith('.py')])
    while len(backups) > 10:
        os.remove(os.path.join(BACKUP_DIR, backups.pop(0)))
    return backup_file

def get_last_backup():
    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith('.py')])
    if backups:
        with open(os.path.join(BACKUP_DIR, backups[-1]), "r", encoding="utf-8") as f:
            return f.read()
    return None

# ===== ПРОВЕРКА КЛЮЧЕЙ =====
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
RENDER_API_KEY = os.environ.get("RENDER_API_KEY")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "carzyben94/Bugaga")
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

log_agent_action("bot_start", "Бот запущен", "success")

# ===== МОДЕЛИ =====
FREE_MODELS = [
    "openrouter/free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-ultra:free",
    "openai/gpt-oss-120b:free",
    "openai/gpt-oss-20b:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "poolside/laguna-m1:free",
    "poolside/laguna-xs2:free",
    "z-ai/glm-4.5-air:free",
    "moonshotai/kimi-k2.6:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "nvidia/nemotron-3-nano-omni:free",
    "deepseek/deepseek-r1:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-coder:free",
]

def ask_ai(prompt, model_index=0):
    if model_index >= len(FREE_MODELS):
        return "😵 Все модели недоступны"
    
    model = FREE_MODELS[model_index]
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 1000}
    
    try:
        response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=45)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        elif response.status_code in (429, 402):
            return ask_ai(prompt, model_index + 1)
        else:
            return ask_ai(prompt, model_index + 1)
    except:
        return ask_ai(prompt, model_index + 1)

# ===== GITHUB ФУНКЦИИ =====
def github_get_file(path):
    if not GITHUB_TOKEN:
        return None
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            return {"content": content, "sha": data["sha"]}
    except:
        pass
    return None

def github_update_file(path, content, commit_msg):
    if not GITHUB_TOKEN:
        return False
    current = github_get_file(path)
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Content-Type": "application/json"}
    payload = {"message": commit_msg, "content": base64.b64encode(content.encode()).decode(), "branch": "main"}
    if current:
        payload["sha"] = current["sha"]
    try:
        resp = requests.put(url, headers=headers, json=payload, timeout=30)
        if resp.status_code in (200, 201):
            log_agent_action("github_write", f"{path}", "success")
            return True
    except:
        pass
    return False

# ===== RENDER ФУНКЦИИ =====
def render_restart():
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        return False
    url = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/restart"
    headers = {"Authorization": f"Bearer {RENDER_API_KEY}"}
    try:
        resp = requests.post(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            log_agent_action("render_restart", "Сервер перезапущен", "success")
            return True
    except:
        pass
    return False

def validate_code_syntax(code):
    try:
        compile(code, '<string>', 'exec')
        return True, None
    except SyntaxError as e:
        return False, str(e)

def test_code_in_sandbox(code):
    try:
        compile(code, '<string>', 'exec')
        if 'while True:' in code and 'break' not in code and 'time.sleep' not in code:
            return False, "Потенциальный бесконечный цикл"
        return True, "OK"
    except SyntaxError as e:
        return False, str(e)

# ===== АВТОМОНИТОРИНГ =====
def auto_monitoring():
    consecutive_errors = 0
    last_auto_fix = 0
    
    while True:
        time.sleep(300)
        
        try:
            if not RENDER_API_KEY:
                continue
            
            url = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/logs?limit=50"
            headers = {"Authorization": f"Bearer {RENDER_API_KEY}"}
            resp = requests.get(url, headers=headers, timeout=30)
            
            if resp.status_code == 200:
                logs = resp.text
                has_error = 'ERROR' in logs or 'Traceback' in logs or 'Exception' in logs
                
                if has_error:
                    consecutive_errors += 1
                    log_agent_action("auto_monitor", f"Ошибка #{consecutive_errors}", "warning")
                    
                    if consecutive_errors >= 3 and (time.time() - last_auto_fix) > 600:
                        log_agent_action("auto_monitor", "Автоисправление", "warning")
                        rollback()
                        last_auto_fix = time.time()
                        consecutive_errors = 0
                else:
                    consecutive_errors = 0
        except:
            pass

monitoring_thread = threading.Thread(target=auto_monitoring, daemon=True)
monitoring_thread.start()

def rollback():
    last_good = get_last_backup()
    if last_good:
        if github_update_file("bot.py", last_good, "АВТООТКАТ"):
            render_restart()
            return True
    return False

# ===== КОМАНДЫ =====
@bot.message_handler(commands=['help'])
def help_command(message):
    menu = """📋 **КОМАНДЫ БОТА**

**🤖 ОСНОВНЫЕ:**
/ai [вопрос] - спросить ИИ
/models - список моделей

**🛠️ УПРАВЛЕНИЕ:**
/addcmd [описание] - добавить команду
/delcmd [название] - удалить команду
/replace [код] или ответ на файл - заменить код бота
/update [код] - обновить код
/restart - перезапустить
/rollback - откат к бэкапу

**📊 МОНИТОРИНГ:**
/health - состояние
/status - статус ключей
/logs - логи действий
/analyze_errors - анализ ошибок

**💾 БЭКАПЫ:**
/backups - список бэкапов
/test [код] - проверить код
/clearlogs - очистить логи

"""
    user_cmds = load_user_commands()
    if user_cmds:
        menu += "\n**➕ ПОЛЬЗОВАТЕЛЬСКИЕ:**\n"
        for cmd in user_cmds:
            menu += f"/{cmd['name']} - {cmd['description']}\n"
    bot.reply_to(message, menu, parse_mode="Markdown")

@bot.message_handler(commands=['replace'])
def replace_command(message):
    """Заменяет код бота на присланный файл или текст"""
    
    new_code = None
    source = None
    
    # Проверяем ответ на файл
    if message.reply_to_message:
        if message.reply_to_message.document:
            file_info = bot.get_file(message.reply_to_message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            new_code = downloaded_file.decode('utf-8')
            source = "файла"
        elif message.reply_to_message.text:
            new_code = message.reply_to_message.text
            source = "текста из ответа"
    
    # Если нет ответа, берём текст из команды
    if not new_code:
        new_code = message.text.replace('/replace', '').strip()
        if new_code:
            source = "текста команды"
    
    if not new_code:
        bot.reply_to(message, "❌ Отправь новый код:\n1. Как текст после /replace\n2. Или пришли файл .py и ответь на него /replace")
        return
    
    status_msg = bot.reply_to(message, f"🔄 Получил код из {source}, проверяю...")
    
    # Проверяем синтаксис
    ok, err = validate_code_syntax(new_code)
    if not ok:
        bot.edit_message_text(f"❌ Ошибка синтаксиса:\n```\n{err}\n```", 
                              chat_id=message.chat.id, message_id=status_msg.message_id,
                              parse_mode="Markdown")
        return
    
    # Сохраняем бэкап
    current = github_get_file("bot.py")
    if current:
        save_backup(current["content"], f"перед /replace от {message.from_user.username}")
    
    # Сохраняем новый код
    if github_update_file("bot.py", new_code, f"Replace via Telegram from {message.from_user.username}"):
        bot.edit_message_text("✅ Код обновлён!\n🔄 Перезапускаю сервер...", 
                              chat_id=message.chat.id, message_id=status_msg.message_id)
        render_restart()
    else:
        bot.edit_message_text("❌ Ошибка сохранения на GitHub\nПроверь GITHUB_TOKEN", 
                              chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['ai'])
def ai_command(message):
    user_text = message.text.replace('/ai', '').strip()
    if not user_text:
        bot.reply_to(message, "/ai [вопрос]")
        return
    status_msg = bot.reply_to(message, "🤔 Думаю...")
    answer = ask_ai(user_text)
    bot.edit_message_text(answer, chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['models'])
def models_command(message):
    models_list = "\n".join([f"• {m.replace(':free', '')}" for m in FREE_MODELS])
    bot.reply_to(message, f"🤖 **Модели (16 шт):**\n\n{models_list}")

@bot.message_handler(commands=['addcmd'])
def addcmd_command(message):
    user_input = message.text.replace('/addcmd', '').strip()
    if not user_input:
        bot.reply_to(message, "❌ /addcmd команда [название] [действие]\nПример: /addcmd команда hello отвечает Привет")
        return
    
    status_msg = bot.reply_to(message, "🔧 Создаю команду...")
    
    current = github_get_file("bot.py")
    if not current:
        bot.edit_message_text("❌ Не могу прочитать код", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    cmd_name_match = re.search(r'команда\s+(\w+)', user_input)
    if not cmd_name_match:
        bot.edit_message_text("❌ Укажи название команды.\nПример: команда hello отвечает Привет", 
                              chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    cmd_name = cmd_name_match.group(1)
    PROTECTED = ['help', 'ai', 'models', 'addcmd', 'delcmd', 'replace', 'update', 'restart', 'rollback', 'backups', 'test', 'health', 'status', 'logs', 'clearlogs', 'analyze_errors']
    
    if cmd_name in PROTECTED:
        bot.edit_message_text(f"❌ Команда /{cmd_name} защищена", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    prompt = f"""Создай команду для Telegram бота. Описание: {user_input}
Верни ТОЛЬКО код:
@bot.message_handler(commands=['{cmd_name}'])
def {cmd_name}_command(message):
    bot.reply_to(message, "ответ")"""
    
    new_command = ask_ai(prompt)
    if not new_command or len(new_command) < 20:
        bot.edit_message_text("❌ Не удалось создать команду", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    old_code = current["content"]
    save_backup(old_code, f"перед добавлением /{cmd_name}")
    
    lines = old_code.split('\n')
    insert_pos = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        if '@bot.message_handler' in lines[i]:
            insert_pos = i
            break
    
    new_lines = lines[:insert_pos] + [new_command] + lines[insert_pos:]
    new_code = '\n'.join(new_lines)
    
    ok, err = test_code_in_sandbox(new_code)
    if not ok:
        bot.edit_message_text(f"❌ Ошибка в песочнице: {err}", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    ok, err = validate_code_syntax(new_code)
    if not ok:
        bot.edit_message_text(f"❌ Ошибка синтаксиса: {err}", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    if github_update_file("bot.py", new_code, f"Добавлена команда /{cmd_name}"):
        save_user_command(cmd_name, user_input[:50])
        bot.edit_message_text(f"✅ Команда /{cmd_name} добавлена!\n🔄 Перезапуск...", 
                              chat_id=message.chat.id, message_id=status_msg.message_id)
        render_restart()
    else:
        bot.edit_message_text("❌ Ошибка сохранения на GitHub", chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['delcmd'])
def delcmd_command(message):
    args = message.text.replace('/delcmd', '').strip().split()
    if not args:
        bot.reply_to(message, "❌ /delcmd [название]\nПример: /delcmd hello")
        return
    
    cmd_to_delete = args[0].lower()
    PROTECTED = ['help', 'ai', 'models', 'addcmd', 'delcmd', 'replace', 'update', 'restart', 'rollback', 'backups', 'test', 'health', 'status', 'logs', 'clearlogs', 'analyze_errors']
    
    if cmd_to_delete in PROTECTED:
        bot.reply_to(message, f"❌ Команда /{cmd_to_delete} защищена")
        return
    
    status_msg = bot.reply_to(message, f"🗑️ Удаляю команду /{cmd_to_delete}...")
    
    current = github_get_file("bot.py")
    if not current:
        bot.edit_message_text("❌ Не могу прочитать код", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    save_backup(current["content"], f"перед удалением /{cmd_to_delete}")
    
    lines = current["content"].split('\n')
    new_lines = []
    deleted = False
    i = 0
    
    while i < len(lines):
        line = lines[i]
        if f"commands=['{cmd_to_delete}']" in line or f'commands=["{cmd_to_delete}"]' in line:
            deleted = True
            i += 2
            while i < len(lines) and not lines[i].strip().startswith('@') and not lines[i].strip().startswith('def '):
                i += 1
            continue
        new_lines.append(line)
        i += 1
    
    if not deleted:
        bot.edit_message_text(f"❌ Команда /{cmd_to_delete} не найдена", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    new_code = '\n'.join(new_lines)
    ok, err = validate_code_syntax(new_code)
    if not ok:
        bot.edit_message_text(f"❌ Ошибка синтаксиса: {err}", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    if github_update_file("bot.py", new_code, f"Удалена команда /{cmd_to_delete}"):
        delete_user_command(cmd_to_delete)
        bot.edit_message_text(f"✅ Команда /{cmd_to_delete} удалена!\n🔄 Перезапуск...", 
                              chat_id=message.chat.id, message_id=status_msg.message_id)
        render_restart()
    else:
        bot.edit_message_text("❌ Ошибка сохранения", chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['update'])
def update_command(message):
    new_code = message.text.replace('/update', '').strip()
    if not new_code:
        bot.reply_to(message, "❌ /update [новый_код]")
        return
    
    status_msg = bot.reply_to(message, "🔄 Обновляю код...")
    
    ok, err = test_code_in_sandbox(new_code)
    if not ok:
        bot.edit_message_text(f"❌ Ошибка в песочнице: {err}", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    current = github_get_file("bot.py")
    if current:
        save_backup(current["content"], "перед /update")
    
    ok, err = validate_code_syntax(new_code)
    if not ok:
        bot.edit_message_text(f"❌ Ошибка синтаксиса: {err}", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    if github_update_file("bot.py", new_code, "Обновление через /update"):
        bot.edit_message_text("✅ Код обновлён!\n🔄 Перезапуск...", chat_id=message.chat.id, message_id=status_msg.message_id)
        render_restart()
    else:
        bot.edit_message_text("❌ Ошибка сохранения", chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['rollback'])
def rollback_command(message):
    status_msg = bot.reply_to(message, "🔄 Выполняю откат...")
    if rollback():
        bot.edit_message_text("✅ Откат выполнен! Бот перезапускается...", 
                              chat_id=message.chat.id, message_id=status_msg.message_id)
    else:
        bot.edit_message_text("❌ Нет сохранённых бэкапов", chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['backups'])
def backups_command(message):
    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith('.py')])
    if backups:
        text = "📦 **Сохранённые бэкапы:**\n\n"
        for b in backups[-10:]:
            text += f"• {b}\n"
        bot.reply_to(message, text)
    else:
        bot.reply_to(message, "📭 Нет бэкапов")

@bot.message_handler(commands=['restart'])
def restart_command(message):
    status_msg = bot.reply_to(message, "🔄 Перезапускаю сервер...")
    if render_restart():
        bot.edit_message_text("✅ Сервер перезапущен", chat_id=message.chat.id, message_id=status_msg.message_id)
    else:
        bot.edit_message_text("❌ Не удалось перезапустить", chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['test'])
def test_command(message):
    code = message.text.replace('/test', '').strip()
    if not code:
        bot.reply_to(message, "❌ /test [код]")
        return
    
    status_msg = bot.reply_to(message, "🧪 Тестирую код...")
    ok, msg = test_code_in_sandbox(code)
    if ok:
        bot.edit_message_text("✅ Тест пройден! Код корректен.", chat_id=message.chat.id, message_id=status_msg.message_id)
    else:
        bot.edit_message_text(f"❌ Тест не пройден:\n{msg}", chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['health'])
def health_command(message):
    uptime = int(time.time() - start_time)
    hours = uptime // 3600
    minutes = (uptime % 3600) // 60
    
    logs = get_agent_logs(500)
    errors = sum(1 for log in logs if log.get("status") == "error")
    backups_count = len([f for f in os.listdir(BACKUP_DIR) if f.endswith('.py')])
    
    status = f"""📊 **Мониторинг бота**

⏱️ Время работы: {hours}ч {minutes}м
✅ Успешность: {round((len(logs)-errors)/max(len(logs),1)*100)}%
❌ Ошибок: {errors}
📦 Бэкапов: {backups_count}

🔑 API ключи:
• GitHub: {'✅' if GITHUB_TOKEN else '❌'}
• Render: {'✅' if RENDER_API_KEY else '❌'}
• OpenRouter: {'✅' if OPENROUTER_API_KEY else '❌'}

🤖 Моделей: {len(FREE_MODELS)}
➕ Пользовательских команд: {len(load_user_commands())}"""
    bot.reply_to(message, status)

@bot.message_handler(commands=['status'])
def status_command(message):
    status = f"""📊 **Статус бота**

GitHub: {'✅' if GITHUB_TOKEN else '❌'}
Render: {'✅' if RENDER_API_KEY else '❌'}
OpenRouter: {'✅' if OPENROUTER_API_KEY else '❌'}

Репозиторий: {GITHUB_REPO or 'не задан'}
Сервис: {RENDER_SERVICE_ID or 'не задан'}
Моделей: {len(FREE_MODELS)}
Бэкапов: {len([f for f in os.listdir(BACKUP_DIR) if f.endswith('.py')])}
Пользовательских команд: {len(load_user_commands())}"""
    bot.reply_to(message, status)

@bot.message_handler(commands=['logs'])
def logs_command(message):
    logs = get_agent_logs(20)
    if not logs:
        bot.reply_to(message, "📭 Логов пока нет")
        return
    text = "📋 **Последние действия агента:**\n\n"
    for log in logs[-15:]:
        if "raw" in log:
            text += f"• {log['raw'][:80]}\n"
        else:
            emoji = "✅" if log.get("status") == "success" else "🔴" if log.get("status") == "error" else "ℹ️"
            text += f"{emoji} {log.get('action', '')}\n"
    bot.reply_to(message, text[:4000])

@bot.message_handler(commands=['clearlogs'])
def clearlogs_command(message):
    if clear_agent_logs():
        bot.reply_to(message, "✅ Логи очищены")
    else:
        bot.reply_to(message, "❌ Ошибка очистки логов")

@bot.message_handler(commands=['analyze_errors'])
def analyze_errors_command(message):
    counts = analyze_error_frequency()
    if not counts:
        bot.reply_to(message, "📊 Ошибок не обнаружено")
        return
    
    report = "📊 **Анализ ошибок:**\n\n"
    for error_type, count in sorted(counts.items(), key=lambda x: -x[1]):
        report += f"• {error_type}: {count} раз\n"
    
    if any(c >= 5 for c in counts.values()):
        report += "\n⚠️ **Внимание:** частые ошибки! Используй /rollback для отката"
    
    bot.reply_to(message, report)

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
def health_check():
    return 'OK', 200

@app.route('/')
def index():
    return 'Telegram Bot is running!', 200

# ===== ЗАПУСК =====
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    render_url = os.environ.get('RENDER_EXTERNAL_URL', f"http://localhost:{port}")
    webhook_url = f"{render_url}/{TELEGRAM_TOKEN}"
    
    logger.info("Удаляем старый вебхук...")
    bot.remove_webhook()
    
    logger.info(f"Устанавливаем новый вебхук: {webhook_url}")
    bot.set_webhook(url=webhook_url)
    
    logger.info(f"🚀 Запускаем Flask сервер на порту {port}")
    app.run(host='0.0.0.0', port=port)
