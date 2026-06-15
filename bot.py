import os
import logging
import requests
import json
import base64
import time
import re
from datetime import datetime
from flask import Flask, request
import telebot

# ===== НАСТРОЙКА ЛОГОВ =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== ЛОГИ ДЕЙСТВИЙ АГЕНТА =====
AGENT_LOG_FILE = "agent_actions.log"
start_time = time.time()

def log_agent_action(action, details=None, status="info"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {"timestamp": timestamp, "action": action, "status": status, "details": details}
    try:
        with open(AGENT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        logger.info(f"[ЛОГ] {action}: {details}")
    except Exception as e:
        logger.error(f"Не удалось записать лог: {e}")

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
    except Exception as e:
        log_agent_action("github_error", str(e), "error")
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
            log_agent_action("github_write", f"{path}: {commit_msg[:50]}", "success")
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
            log_agent_action("render_restart", f"Сервис {RENDER_SERVICE_ID}", "success")
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

# ===== ОСНОВНЫЕ КОМАНДЫ =====
@bot.message_handler(commands=['help'])
def help_command(message):
    menu = """📋 **Команды бота:**

/ai [вопрос] - спросить ИИ
/hello [текст] - команда hello отвечает Привет

/models - список моделей

**🔄 Управление командами:**
/addcmd [описание] - добавить новую команду
/delcmd [название] - удалить команду

**🔧 Управление ботом:**
/update [код] - обновить код
/restart - перезапустить сервер

**📊 Мониторинг:**
/health - состояние бота
/status - статус ключей
/logs - логи агента
/clearlogs - очистить логи"""
    bot.reply_to(message, menu, parse_mode="Markdown")

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

# ===== ДОБАВЛЕНИЕ КОМАНДЫ =====
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
    
    prompt = f"""Создай команду для Telegram бота. Описание: {user_input}
Верни ТОЛЬКО код:
@bot.message_handler(commands=['{cmd_name}'])
def {cmd_name}_command(message):
    bot.reply_to(message, "ответ")"""
    
    new_command = ask_ai(prompt)
    if not new_command or len(new_command) < 20:
        bot.edit_message_text("❌ Не удалось создать", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    old_code = current["content"]
    lines = old_code.split('\n')
    
    insert_pos = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        if '@bot.message_handler' in lines[i]:
            insert_pos = i
            break
    
    new_lines = lines[:insert_pos] + [new_command] + lines[insert_pos:]
    
    # Добавляем в меню
    for i, line in enumerate(new_lines):
        if 'def help_command(message):' in line:
            for j in range(i, min(i + 30, len(new_lines))):
                if '/ai [вопрос]' in new_lines[j]:
                    indent = len(new_lines[j]) - len(new_lines[j].lstrip())
                    new_cmd_line = ' ' * indent + f'/{cmd_name} [текст] - {user_input[:30]}\n'
                    new_lines.insert(j + 1, new_cmd_line)
                    break
            break
    
    new_code = '\n'.join(new_lines)
    is_valid, error = validate_code_syntax(new_code)
    if not is_valid:
        bot.edit_message_text(f"❌ Ошибка: {error}", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    if github_update_file("bot.py", new_code, f"Добавлена /{cmd_name}"):
        bot.edit_message_text(f"✅ Команда /{cmd_name} добавлена!\n🔄 Перезапуск...", 
                              chat_id=message.chat.id, message_id=status_msg.message_id)
        render_restart()
    else:
        bot.edit_message_text("❌ Ошибка", chat_id=message.chat.id, message_id=status_msg.message_id)

# ===== УДАЛЕНИЕ КОМАНДЫ =====
@bot.message_handler(commands=['delcmd'])
def delcmd_command(message):
    args = message.text.replace('/delcmd', '').strip().split()
    if not args:
        bot.reply_to(message, "❌ /delcmd [название]\nПример: /delcmd hello")
        return
    
    cmd_to_delete = args[0].lower().replace('/', '')
    PROTECTED = ['help', 'ai', 'models', 'addcmd', 'delcmd', 'update', 'restart', 'health', 'status', 'logs', 'clearlogs']
    
    if cmd_to_delete in PROTECTED:
        bot.reply_to(message, f"❌ /{cmd_to_delete} защищена")
        return
    
    status_msg = bot.reply_to(message, f"🗑️ Удаляю /{cmd_to_delete}...")
    
    current = github_get_file("bot.py")
    if not current:
        bot.edit_message_text("❌ Ошибка", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    old_code = current["content"]
    lines = old_code.split('\n')
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
        if f'/{cmd_to_delete}' in line and 'def help_command' not in str(line):
            i += 1
            continue
        new_lines.append(line)
        i += 1
    
    if not deleted:
        bot.edit_message_text(f"❌ /{cmd_to_delete} не найдена", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    new_code = '\n'.join(new_lines)
    is_valid, error = validate_code_syntax(new_code)
    if not is_valid:
        bot.edit_message_text(f"❌ Ошибка: {error}", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    if github_update_file("bot.py", new_code, f"Удалена /{cmd_to_delete}"):
        bot.edit_message_text(f"✅ /{cmd_to_delete} удалена!\n🔄 Перезапуск...", 
                              chat_id=message.chat.id, message_id=status_msg.message_id)
        render_restart()
    else:
        bot.edit_message_text("❌ Ошибка", chat_id=message.chat.id, message_id=status_msg.message_id)

# ===== УПРАВЛЕНИЕ =====
@bot.message_handler(commands=['update'])
def update_command(message):
    new_code = message.text.replace('/update', '').strip()
    if not new_code:
        bot.reply_to(message, "❌ /update [код]")
        return
    
    status_msg = bot.reply_to(message, "🔄 Обновляю...")
    is_valid, error = validate_code_syntax(new_code)
    if not is_valid:
        bot.edit_message_text(f"❌ {error}", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    if github_update_file("bot.py", new_code, "Обновление через /update"):
        bot.edit_message_text("✅ Обновлено!\n🔄 Перезапуск...", chat_id=message.chat.id, message_id=status_msg.message_id)
        render_restart()
    else:
        bot.edit_message_text("❌ Ошибка", chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['restart'])
def restart_command(message):
    status_msg = bot.reply_to(message, "🔄 Перезапуск...")
    if render_restart():
        bot.edit_message_text("✅ Перезапущено", chat_id=message.chat.id, message_id=status_msg.message_id)
    else:
        bot.edit_message_text("❌ Ошибка", chat_id=message.chat.id, message_id=status_msg.message_id)

# ===== МОНИТОРИНГ =====
@bot.message_handler(commands=['health'])
def health_command(message):
    uptime = int(time.time() - start_time)
    hours = uptime // 3600
    minutes = (uptime % 3600) // 60
    
    logs = get_agent_logs(500)
    errors = sum(1 for log in logs if log.get("status") == "error")
    
    status = f"""📊 **Мониторинг**

⏱️ Работает: {hours}ч {minutes}м
✅ Успешность: {round((len(logs)-errors)/max(len(logs),1)*100)}%
❌ Ошибок: {errors}

🔑 Ключи:
• GitHub: {'✅' if GITHUB_TOKEN else '❌'}
• Render: {'✅' if RENDER_API_KEY else '❌'}
• OpenRouter: {'✅' if OPENROUTER_API_KEY else '❌'}

🤖 Моделей: {len(FREE_MODELS)}"""
    bot.reply_to(message, status)

@bot.message_handler(commands=['status'])
def status_command(message):
    status = f"""📊 **Статус**

GitHub: {'✅' if GITHUB_TOKEN else '❌'}
Render: {'✅' if RENDER_API_KEY else '❌'}
Репозиторий: {GITHUB_REPO or 'не задан'}
Сервис: {RENDER_SERVICE_ID or 'не задан'}
Моделей: {len(FREE_MODELS)}"""
    bot.reply_to(message, status)

@bot.message_handler(commands=['logs'])
def logs_command(message):
    logs = get_agent_logs(20)
    if not logs:
        bot.reply_to(message, "📭 Логов нет")
        return
    text = "📋 **Последние действия:**\n\n"
    for log in logs[-15:]:
        if "raw" in log:
            text += f"• {log['raw'][:80]}\n"
        else:
            emoji = "✅" if log.get("status") == "success" else "🔴" if log.get("status") == "error" else "ℹ️"
            text += f"{emoji} {log.get('action', '')}\n"
    bot.reply_to(message, text[:4000])

@bot.message_handler(commands=['hello'])
def hello_command(message):
    bot.reply_to(message, "Привет")
@bot.message_handler(commands=['clearlogs'])
def clearlogs_command(message):
    if clear_agent_logs():
        bot.reply_to(message, "✅ Логи очищены")
    else:
        bot.reply_to(message, "❌ Ошибка")

# ===== ВЕБХУК =====
@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
        bot.process_new_updates([update])
        return 'ok', 200
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return 'error', 500

@app.route('/health')
def health_check():
    return 'OK', 200

# ===== ЗАПУСК =====
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    render_url = os.environ.get('RENDER_EXTERNAL_URL', f"http://localhost:{port}")
    webhook_url = f"{render_url}/{TELEGRAM_TOKEN}"
    
    bot.remove_webhook()
    bot.set_webhook(url=webhook_url)
    
    app.run(host='0.0.0.0', port=port)
