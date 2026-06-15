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
BACKUP_DIR = "backups"
start_time = time.time()

os.makedirs(BACKUP_DIR, exist_ok=True)

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
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 500}
    
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

def rollback():
    last_good = get_last_backup()
    if last_good:
        if github_update_file("bot.py", last_good, "АВТООТКАТ"):
            render_restart()
            return True
    return False

# ===== КОМАНДЫ =====
@bot.message_handler(commands=['menu', 'help', 'start'])
def menu_command(message):
    menu = """📋 **МЕНЮ БОТА**

**🧠 ИИ И ПОИСК**
/ai [вопрос] — спросить ИИ

**🛠️ УПРАВЛЕНИЕ**
/replace — заменить код (файл + /replace)
/restart — перезапустить
/rollback — откат к бэкапу

**📊 МОНИТОРИНГ**
/health — состояние бота (всё в одном)
/logs — логи действий
/analyze_errors — анализ ошибок"""
    bot.reply_to(message, menu)

@bot.message_handler(commands=['ai'])
def ai_command(message):
    user_text = message.text.replace('/ai', '').strip()
    if not user_text:
        bot.reply_to(message, "/ai [вопрос]")
        return
    status_msg = bot.reply_to(message, "🤔 Думаю...")
    answer = ask_ai(user_text)
    bot.edit_message_text(answer, chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['replace'])
def replace_command(message):
    new_code = None
    
    if message.reply_to_message and message.reply_to_message.document:
        file_info = bot.get_file(message.reply_to_message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        new_code = downloaded_file.decode('utf-8')
    
    if not new_code:
        bot.reply_to(message, "❌ Отправь файл bot.py и ответь на него /replace")
        return
    
    status_msg = bot.reply_to(message, "🔄 Проверяю и заменяю код...")
    
    ok, err = validate_code_syntax(new_code)
    if not ok:
        bot.edit_message_text(f"❌ Ошибка синтаксиса:\n{err}", 
                              chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    current = github_get_file("bot.py")
    if current:
        save_backup(current["content"], "перед /replace")
    
    if github_update_file("bot.py", new_code, "Replace via Telegram"):
        bot.edit_message_text("✅ Код обновлён!\n🔄 Перезапускаю сервер...", 
                              chat_id=message.chat.id, message_id=status_msg.message_id)
        render_restart()
    else:
        bot.edit_message_text("❌ Ошибка сохранения на GitHub", 
                              chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['restart'])
def restart_command(message):
    status_msg = bot.reply_to(message, "🔄 Перезапускаю сервер...")
    if render_restart():
        bot.edit_message_text("✅ Сервер перезапущен", chat_id=message.chat.id, message_id=status_msg.message_id)
    else:
        bot.edit_message_text("❌ Не удалось перезапустить", chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['rollback'])
def rollback_command(message):
    status_msg = bot.reply_to(message, "🔄 Выполняю откат...")
    if rollback():
        bot.edit_message_text("✅ Откат выполнен! Бот перезапускается...", 
                              chat_id=message.chat.id, message_id=status_msg.message_id)
    else:
        bot.edit_message_text("❌ Нет сохранённых бэкапов", chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['health'])
def health_command(message):
    uptime = int(time.time() - start_time)
    hours = uptime // 3600
    minutes = (uptime % 3600) // 60
    
    logs = get_agent_logs(500)
    errors = sum(1 for log in logs if log.get("status") == "error")
    backups_count = len([f for f in os.listdir(BACKUP_DIR) if f.endswith('.py')])
    
    status = f"""📊 **СОСТОЯНИЕ БОТА**

⏱️ Работает: {hours}ч {minutes}м
✅ Успешность: {round((len(logs)-errors)/max(len(logs),1)*100)}%
❌ Ошибок: {errors}
📦 Бэкапов: {backups_count}

🔑 **КЛЮЧИ:**
GitHub: {'✅' if GITHUB_TOKEN else '❌'}
Render: {'✅' if RENDER_API_KEY else '❌'}
OpenRouter: {'✅' if OPENROUTER_API_KEY else '❌'}"""
    bot.reply_to(message, status)

@bot.message_handler(commands=['logs'])
def logs_command(message):
    logs = get_agent_logs(20)
    if not logs:
        bot.reply_to(message, "📭 Логов пока нет")
        return
    text = "📋 Последние действия:\n\n"
    for log in logs[-15:]:
        if "raw" in log:
            text += f"• {log['raw'][:80]}\n"
        else:
            emoji = "✅" if log.get("status") == "success" else "🔴" if log.get("status") == "error" else "ℹ️"
            text += f"{emoji} {log.get('action', '')}\n"
    bot.reply_to(message, text[:4000])

@bot.message_handler(commands=['analyze_errors'])
def analyze_errors_command(message):
    logs = get_agent_logs(500)
    errors = [log for log in logs if log.get("status") == "error"]
    
    if not errors:
        bot.reply_to(message, "📊 Ошибок не обнаружено")
        return
    
    error_types = {}
    for err in errors[-20:]:
        error_type = err.get("action", "unknown")
        error_types[error_type] = error_types.get(error_type, 0) + 1
    
    report = "📊 **Анализ ошибок (последние 20):**\n\n"
    for error_type, count in sorted(error_types.items(), key=lambda x: -x[1]):
        report += f"• {error_type}: {count} раз\n"
    
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    render_url = os.environ.get('RENDER_EXTERNAL_URL', f"http://localhost:{port}")
    webhook_url = f"{render_url}/{TELEGRAM_TOKEN}"
    
    bot.remove_webhook()
    bot.set_webhook(url=webhook_url)
    
    app.run(host='0.0.0.0', port=port)
