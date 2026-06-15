import os
import logging
import requests
import json
import base64
import time
from datetime import datetime
from flask import Flask, request
import telebot

# ===== НАСТРОЙКА ЛОГОВ =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== ЛОГИ ДЕЙСТВИЙ АГЕНТА =====
AGENT_LOG_FILE = "agent_actions.log"

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


TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# ===== ДОПОЛНИТЕЛЬНЫЕ ПЕРЕМЕННЫЕ ДЛЯ РЕКУРСИВНОСТИ =====
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
RENDER_API_KEY = os.environ.get("RENDER_API_KEY")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "carzyben94/Bugaga")
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# Логируем запуск бота
log_agent_action("bot_start", f"Бот запущен на Render", "info")

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


# ===== ФУНКЦИИ ДЛЯ РЕКУРСИВНОСТИ (РАБОТА С GITHUB И RENDER) =====
def github_get_file(path):
    """Получает файл из репозитория"""
    if not GITHUB_TOKEN:
        log_agent_action("github_error", "Нет GITHUB_TOKEN", "error")
        return None
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            log_agent_action("github_read", f"Файл {path}", "success")
            return {"content": content, "sha": data["sha"]}
        else:
            log_agent_action("github_read_error", f"Статус {resp.status_code}", "error")
    except Exception as e:
        log_agent_action("github_exception", str(e), "error")
    return None

def github_update_file(path, content, commit_msg):
    """Обновляет файл в репозитории"""
    if not GITHUB_TOKEN:
        log_agent_action("github_error", "Нет GITHUB_TOKEN", "error")
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
            log_agent_action("github_write", f"Файл {path}: {commit_msg}", "success")
            return True
        else:
            log_agent_action("github_write_error", f"Статус {resp.status_code}", "error")
    except Exception as e:
        log_agent_action("github_exception", str(e), "error")
    return False

def render_restart():
    """Перезапускает сервис на Render"""
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        log_agent_action("render_error", "Нет RENDER_API_KEY или RENDER_SERVICE_ID", "error")
        return False
    url = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/restart"
    headers = {"Authorization": f"Bearer {RENDER_API_KEY}"}
    try:
        resp = requests.post(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            log_agent_action("render_restart", f"Сервис {RENDER_SERVICE_ID} перезапущен", "success")
            return True
        else:
            log_agent_action("render_restart_error", f"Статус {resp.status_code}", "error")
    except Exception as e:
        log_agent_action("render_exception", str(e), "error")
    return False

def validate_code_syntax(code):
    """Проверяет синтаксис Python кода"""
    try:
        compile(code, '<string>', 'exec')
        return True, None
    except SyntaxError as e:
        return False, str(e)

def recursive_update(new_code, attempt=1, max_attempts=3):
    """Рекурсивно обновляет код, проверяя синтаксис"""
    log_agent_action("recursive_update_start", f"Попытка {attempt}/{max_attempts}", "info")
    
    # Проверяем синтаксис
    is_valid, error = validate_code_syntax(new_code)
    if not is_valid:
        log_agent_action("syntax_error", error, "error")
        if attempt < max_attempts:
            # Просим ИИ исправить ошибку
            prompt = f"Исправь синтаксическую ошибку в этом коде: {error}\n\nКод:\n{new_code}\n\nВерни только исправленный код."
            fixed_code = ask_ai(prompt)
            if fixed_code and fixed_code != new_code:
                log_agent_action("ai_fix_attempt", f"Попытка {attempt+1}", "info")
                return recursive_update(fixed_code, attempt + 1, max_attempts)
        return False, f"Ошибка синтаксиса: {error}"
    
    # Сохраняем на GitHub
    if not github_update_file("bot.py", new_code, f"Рекурсивное обновление: попытка {attempt}"):
        return False, "Не удалось сохранить код на GitHub"
    
    log_agent_action("recursive_update_success", f"Код обновлён за {attempt} попыток", "success")
    return True, "Код успешно обновлён"


# ===== КОМАНДЫ =====
@bot.message_handler(commands=['help'])
def help_command(message):
    log_agent_action("command_help", f"Пользователь {message.from_user.id}", "info")
    bot.reply_to(
        message,
        "/ai [вопрос] - спросить ИИ\n"
        "/models - список моделей\n"
        "/update [код] - обновить код бота (рекурсивно)\n"
        "/restart - перезапустить сервер\n"
        "/status - показать статус\n"
        "/logs - показать логи действий агента\n"
        "/clearlogs - очистить логи агента"
    )

@bot.message_handler(commands=['ai'])
def ai_command(message):
    user_text = message.text.replace('/ai', '').strip()
    if not user_text:
        bot.reply_to(message, "/ai [вопрос]")
        return
    
    log_agent_action("command_ai", f"Запрос: {user_text[:50]}...", "info")
    bot.send_chat_action(message.chat.id, 'typing')
    status_msg = bot.reply_to(message, "🤔 Думаю...")
    
    answer = ask_ai(user_text)
    
    bot.edit_message_text(answer, chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['models'])
def models_command(message):
    log_agent_action("command_models", f"Пользователь {message.from_user.id}", "info")
    models_list = "\n".join([f"• {m.replace(':free', '')}" for m in FREE_MODELS])
    bot.reply_to(
        message,
        f"🤖 **Модели ИИ:**\n\n{models_list}\n\n"
        f"📊 Всего: {len(FREE_MODELS)} моделей"
    )

@bot.message_handler(commands=['update'])
def update_command(message):
    """Рекурсивное обновление кода бота"""
    new_code = message.text.replace('/update', '').strip()
    if not new_code:
        bot.reply_to(message, "❌ /update [новый_код]")
        return
    
    log_agent_action("command_update", "Начало обновления кода", "info")
    status_msg = bot.reply_to(message, "🔄 Рекурсивно обновляю код...")
    
    success, result = recursive_update(new_code)
    
    if success:
        log_agent_action("update_success", result, "success")
        bot.edit_message_text(
            f"✅ {result}\n🔄 Перезапускаю сервер...",
            chat_id=message.chat.id,
            message_id=status_msg.message_id
        )
        render_restart()
    else:
        log_agent_action("update_failed", result, "error")
        bot.edit_message_text(
            f"❌ {result}",
            chat_id=message.chat.id,
            message_id=status_msg.message_id
        )

@bot.message_handler(commands=['restart'])
def restart_command(message):
    """Перезапуск сервера на Render"""
    log_agent_action("command_restart", f"Пользователь {message.from_user.id}", "info")
    status_msg = bot.reply_to(message, "🔄 Перезапускаю сервер...")
    if render_restart():
        bot.edit_message_text("✅ Сервер перезапущен", chat_id=message.chat.id, message_id=status_msg.message_id)
    else:
        bot.edit_message_text("❌ Не удалось перезапустить", chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['status'])
def status_command(message):
    """Показывает статус переменных окружения"""
    log_agent_action("command_status", f"Пользователь {message.from_user.id}", "info")
    status = f"""📊 **Статус бота**

Репозиторий: {GITHUB_REPO or 'не задан'}
Render сервис: {RENDER_SERVICE_ID or 'не задан'}

API ключи:
GitHub: {'✅' if GITHUB_TOKEN else '❌'}
Render: {'✅' if RENDER_API_KEY else '❌'}
OpenRouter: {'✅' if OPENROUTER_API_KEY else '❌'}

Всего моделей: {len(FREE_MODELS)}
"""
    bot.reply_to(message, status)

@bot.message_handler(commands=['logs'])
def logs_command(message):
    """Показывает логи действий агента"""
    log_agent_action("command_logs", f"Пользователь {message.from_user.id}", "info")
    
    logs = get_agent_logs(30)
    if not logs:
        bot.reply_to(message, "📭 Логов пока нет")
        return
    
    # Форматируем логи для вывода
    log_text = "📋 **Последние действия агента:**\n\n"
    for log in logs:
        if "raw" in log:
            log_text += f"• {log['raw'][:100]}\n"
        else:
            status_emoji = "✅" if log.get("status") == "success" else "⚠️" if log.get("status") == "warning" else "🔴" if log.get("status") == "error" else "ℹ️"
            log_text += f"{status_emoji} `{log.get('timestamp', '')}` **{log.get('action', '')}**\n"
            if log.get("details"):
                details = str(log.get("details"))[:100]
                log_text += f"   → {details}\n"
    
    if len(log_text) > 4000:
        log_text = log_text[:4000] + "..."
    
    bot.reply_to(message, log_text, parse_mode="Markdown")

@bot.message_handler(commands=['clearlogs'])
def clearlogs_command(message):
    """Очищает логи агента"""
    log_agent_action("command_clearlogs", f"Пользователь {message.from_user.id}", "warning")
    
    if clear_agent_logs():
        bot.reply_to(message, "✅ Логи агента очищены")
    else:
        bot.reply_to(message, "❌ Не удалось очистить логи")


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
        log_agent_action("webhook_error", str(e), "error")
        return 'error', 500

@app.route('/health')
def health():
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    render_url = os.environ.get('RENDER_EXTERNAL_URL', f"http://localhost:{port}")
    webhook_url = f"{render_url}/{TELEGRAM_TOKEN}"
    
    logger.info("Удаляем старый вебхук...")
    bot.remove_webhook()
    
    logger.info(f"Устанавливаем новый вебхук: {webhook_url}")
    bot.set_webhook(url=webhook_url)
    
    logger.info(f"🚀 Запускаем Flask на порту {port}")
    log_agent_action("server_start", f"Запуск на порту {port}", "success")
    app.run(host='0.0.0.0', port=port)
