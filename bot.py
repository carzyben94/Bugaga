import os
import logging
import requests
import json
import base64
import time
import threading
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
    """Записывает действие агента в файл логов"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        "timestamp": timestamp,
        "action": action,
        "status": status,
        "details": details
    }
    try:
        with open(AGENT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        logger.info(f"[ЛОГ] {action}: {details}")
    except Exception as e:
        logger.error(f"Не удалось записать лог: {e}")

def get_agent_logs(limit=50):
    """Читает последние логи действий агента"""
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
    except Exception as e:
        return [{"error": str(e)}]

def clear_agent_logs():
    """Очищает логи агента"""
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

# ===== ДОПОЛНИТЕЛЬНЫЕ ПЕРЕМЕННЫЕ =====
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
RENDER_API_KEY = os.environ.get("RENDER_API_KEY")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "carzyben94/Bugaga")
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# Логируем запуск
log_agent_action("bot_start", "Бот запущен", "success")

# ===== АКТУАЛЬНЫЕ БЕСПЛАТНЫЕ МОДЕЛИ (июнь 2026) =====
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
        log_agent_action("ai_error", "Все модели недоступны", "error")
        return "😵 Все бесплатные модели временно недоступны. Попробуйте позже."
    
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
            answer = response.json()["choices"][0]["message"]["content"]
            logger.info(f"✅ Модель {model} ответила успешно")
            return answer
        
        elif response.status_code == 429:
            logger.warning(f"⚠️ Модель {model}: лимит, переключаем...")
            log_agent_action("model_limit", model, "warning")
            return ask_ai(prompt, model_index + 1)
        
        elif response.status_code == 402:
            logger.warning(f"⚠️ Модель {model}: требуется оплата, переключаем...")
            log_agent_action("model_payment_required", model, "warning")
            return ask_ai(prompt, model_index + 1)
        
        else:
            logger.warning(f"⚠️ Модель {model}: ошибка {response.status_code}, переключаем...")
            return ask_ai(prompt, model_index + 1)
            
    except requests.exceptions.Timeout:
        logger.warning(f"⚠️ Модель {model}: таймаут, переключаем...")
        log_agent_action("model_timeout", model, "warning")
        return ask_ai(prompt, model_index + 1)
    except Exception as e:
        logger.error(f"❌ Модель {model}: ошибка {e}, переключаем...")
        log_agent_action("model_error", str(e), "error")
        return ask_ai(prompt, model_index + 1)


# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С GITHUB =====
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
    except Exception as e:
        log_agent_action("github_write_error", str(e), "error")
    return False

# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С RENDER =====
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
    except Exception as e:
        log_agent_action("render_error", str(e), "error")
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
    log_agent_action("help", f"User {message.from_user.id}", "info")
    bot.reply_to(
        message,
        "📋 **Команды бота:**\n\n"
        "**🤖 Основные:**\n"
        "/ai [вопрос] - спросить ИИ\n"
        "/models - список моделей\n\n"
        "**🔄 Управление:**\n"
        "/addcmd [описание] - добавить новую команду\n"
        "/update [код] - обновить код бота\n"
        "/restart - перезапустить сервер\n\n"
        "**📊 Мониторинг:**\n"
        "/health - состояние бота\n"
        "/status - статус ключей\n"
        "/logs - логи агента\n"
        "/clearlogs - очистить логи",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['ai'])
def ai_command(message):
    user_text = message.text.replace('/ai', '').strip()
    if not user_text:
        bot.reply_to(message, "/ai [вопрос]")
        return
    
    log_agent_action("ai_query", user_text[:50], "info")
    bot.send_chat_action(message.chat.id, 'typing')
    status_msg = bot.reply_to(message, "🤔 Думаю...")
    
    answer = ask_ai(user_text)
    bot.edit_message_text(answer, chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['models'])
def models_command(message):
    models_list = "\n".join([f"• {m.replace(':free', '')}" for m in FREE_MODELS])
    bot.reply_to(message, f"🤖 **Модели ИИ (16 шт):**\n\n{models_list}")

# ===== ДОБАВЛЕНИЕ КОМАНД =====
@bot.message_handler(commands=['addcmd'])
def addcmd_command(message):
    user_input = message.text.replace('/addcmd', '').strip()
    if not user_input:
        bot.reply_to(message, "❌ /addcmd [описание команды]\n\nПример: /addcmd команда hello отвечает Привет")
        return
    
    status_msg = bot.reply_to(message, "🔧 Создаю команду...")
    
    current = github_get_file("bot.py")
    if not current:
        bot.edit_message_text("❌ Не могу прочитать код", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    prompt = f"""Создай команду для Telegram бота на Python с telebot.

Описание: {user_input}

Верни ТОЛЬКО код команды. Формат:
@bot.message_handler(commands=['название'])
def название_command(message):
    bot.reply_to(message, "ответ")"""
    
    new_command = ask_ai(prompt)
    
    if not new_command or len(new_command) < 20:
        bot.edit_message_text("❌ Не удалось создать команду", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    old_code = current["content"]
    lines = old_code.split('\n')
    insert_pos = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        if '@bot.message_handler' in lines[i]:
            insert_pos = i
            break
    
    new_lines = lines[:insert_pos] + [new_command] + lines[insert_pos:]
    new_code = '\n'.join(new_lines)
    
    is_valid, error = validate_code_syntax(new_code)
    if not is_valid:
        bot.edit_message_text(f"❌ Ошибка синтаксиса: {error}", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    if github_update_file("bot.py", new_code, f"Добавлена команда: {user_input[:50]}"):
        log_agent_action("addcmd", user_input[:50], "success")
        bot.edit_message_text("✅ Команда добавлена!\n🔄 Перезапуск...", chat_id=message.chat.id, message_id=status_msg.message_id)
        render_restart()
    else:
        bot.edit_message_text("❌ Ошибка сохранения", chat_id=message.chat.id, message_id=status_msg.message_id)

# ===== УПРАВЛЕНИЕ БОТОМ =====
@bot.message_handler(commands=['update'])
def update_command(message):
    new_code = message.text.replace('/update', '').strip()
    if not new_code:
        bot.reply_to(message, "❌ /update [новый_код]")
        return
    
    status_msg = bot.reply_to(message, "🔄 Обновляю код...")
    
    is_valid, error = validate_code_syntax(new_code)
    if not is_valid:
        bot.edit_message_text(f"❌ Ошибка: {error}", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    if github_update_file("bot.py", new_code, "Обновление через /update"):
        log_agent_action("update", "Код обновлён", "success")
        bot.edit_message_text("✅ Код обновлён!\n🔄 Перезапуск...", chat_id=message.chat.id, message_id=status_msg.message_id)
        render_restart()
    else:
        bot.edit_message_text("❌ Ошибка", chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['restart'])
def restart_command(message):
    status_msg = bot.reply_to(message, "🔄 Перезапуск...")
    if render_restart():
        bot.edit_message_text("✅ Сервер перезапущен", chat_id=message.chat.id, message_id=status_msg.message_id)
    else:
        bot.edit_message_text("❌ Ошибка", chat_id=message.chat.id, message_id=status_msg.message_id)

# ===== МОНИТОРИНГ =====
@bot.message_handler(commands=['health'])
def health_command(message):
    uptime_seconds = time.time() - start_time
    uptime_hours = int(uptime_seconds // 3600)
    uptime_minutes = int((uptime_seconds % 3600) // 60)
    
    logs = get_agent_logs(500)
    total_actions = len(logs)
    errors = sum(1 for log in logs if log.get("status") == "error")
    success_rate = round((total_actions - errors) / max(total_actions, 1) * 100)
    
    status = f"""📊 **Мониторинг бота**

⏱️ **Работает:** {uptime_hours}ч {uptime_minutes}м
📈 **Действий:** {total_actions}
✅ **Успешность:** {success_rate}%
❌ **Ошибок:** {errors}

🔑 **Ключи:**
• GitHub: {'✅' if GITHUB_TOKEN else '❌'}
• Render: {'✅' if RENDER_API_KEY else '❌'}
• OpenRouter: {'✅' if OPENROUTER_API_KEY else '❌'}

🤖 **Моделей:** {len(FREE_MODELS)}
📁 **Репозиторий:** {GITHUB_REPO or 'не задан'}
"""
    bot.reply_to(message, status, parse_mode="Markdown")

@bot.message_handler(commands=['status'])
def status_command(message):
    status = f"""📊 **Статус бота**

GitHub: {'✅' if GITHUB_TOKEN else '❌'}
Render: {'✅' if RENDER_API_KEY else '❌'}
OpenRouter: {'✅' if OPENROUTER_API_KEY else '❌'}

Репозиторий: {GITHUB_REPO or 'не задан'}
Сервис: {RENDER_SERVICE_ID or 'не задан'}
Моделей: {len(FREE_MODELS)}
"""
    bot.reply_to(message, status)

@bot.message_handler(commands=['logs'])
def logs_command(message):
    logs = get_agent_logs(30)
    if not logs:
        bot.reply_to(message, "📭 Логов нет")
        return
    
    log_text = "📋 **Последние действия:**\n\n"
    for log in logs[-15:]:
        if "raw" in log:
            log_text += f"• {log['raw'][:80]}\n"
        else:
            emoji = "✅" if log.get("status") == "success" else "⚠️" if log.get("status") == "warning" else "🔴" if log.get("status") == "error" else "ℹ️"
            log_text += f"{emoji} {log.get('action', '')}\n"
    
    bot.reply_to(message, log_text[:4000], parse_mode="Markdown")

@bot.message_handler(commands=['privet'])
def privet_command(message):
    bot.reply_to(message, "привет")
@bot.message_handler(commands=['clearlogs'])
def clearlogs_command(message):
    if clear_agent_logs():
        log_agent_action("clearlogs", "Логи очищены", "info")
        bot.reply_to(message, "✅ Логи очищены")
    else:
        bot.reply_to(message, "❌ Ошибка")

# ===== ВЕБХУК =====
@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        json_str = request.stream.read().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return 'ok', 200
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        log_agent_action("webhook_error", str(e), "error")
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
    
    log_agent_action("server_start", f"Порт {port}", "success")
    app.run(host='0.0.0.0', port=port)
