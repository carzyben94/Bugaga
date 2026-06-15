import os
import time
import logging
import json
import requests
import threading
from flask import Flask, request
import telebot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

with open("start_time.txt", "w") as f:
    f.write(str(time.time()))

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
RENDER_API_KEY = os.environ.get("RENDER_API_KEY")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "carzyben94/Bugaga")
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not set")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# ===== СТАТУС МОДУЛЬ =====
try:
    from status import register_status_full
    register_status_full(bot)
    print("Status module loaded")
except Exception as e:
    print(f"Status not loaded: {e}")

# ===== ЛОГИ В ЧАТ =====
def send_log_to_admin(action, details=None, status="info"):
    """Отправляет лог в Telegram админу"""
    if not ADMIN_CHAT_ID:
        return
    
    emoji = "✅" if status == "success" else "🔴" if status == "error" else "ℹ️"
    timestamp = time.strftime("%H:%M:%S")
    
    try:
        bot.send_message(ADMIN_CHAT_ID, f"{emoji} [{timestamp}] {action}: {details}")
    except:
        pass

def log_action(action, details=None, status="info", send=True):
    """Логирование действия с отправкой в чат"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {"timestamp": timestamp, "action": action, "status": status, "details": details}
    
    # Пишем в файл
    try:
        with open("agent_actions.log", "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except:
        pass
    
    # Отправляем в Telegram
    if send:
        send_log_to_admin(action, details, status)

def get_last_errors(limit=5):
    """Читает последние ошибки из логов"""
    try:
        if not os.path.exists("agent_actions.log"):
            return []
        with open("agent_actions.log", "r") as f:
            lines = f.readlines()
        errors = []
        for line in reversed(lines[-100:]):
            try:
                log = json.loads(line)
                if log.get("status") == "error":
                    errors.append(log.get("details", ""))
                    if len(errors) >= limit:
                        break
            except:
                pass
        return errors
    except:
        return []

# ===== ФУНКЦИИ ДЛЯ ВЕБ-СЕРФИНГА =====
def search_web(query, num_results=3):
    """Поиск в интернете через DuckDuckGo"""
    try:
        from urllib.parse import quote_plus
        search_url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(search_url, headers=headers, timeout=15)
        
        if resp.status_code == 200:
            import re
            results = []
            links = re.findall(r'<a href="(https?://[^"]+)"', resp.text)
            titles = re.findall(r'<td class="result-snippet">([^<]+)‹', resp.text)
            
            for i in range(min(num_results, len(links))):
                title = titles[i] if i < len(titles) else "Результат"
                results.append({"title": title, "url": links[i]})
            return results
        return []
    except Exception as e:
        log_action("search_error", str(e), "error")
        return []

def get_page_content(url):
    """Получает содержимое страницы"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            import re
            text = re.sub(r'<[^>]+>', ' ', resp.text)
            text = re.sub(r'\s+', ' ', text)
            return text[:3000]
        return ""
    except:
        return ""

# ===== ФУНКЦИЯ САМОУЛУЧШЕНИЯ =====
def research_and_improve():
    """Фоновый процесс самообучения"""
    log_action("self_improvement", "Начинаю поиск улучшений", "info")
    
    errors = get_last_errors(3)
    if not errors:
        log_action("self_improvement", "Ошибок не найдено", "success")
        return
    
    error_text = "\n".join(errors)
    log_action("self_improvement", f"Найдены ошибки: {error_text[:200]}", "warning")
    
    search_query = f"Python telebot error fix {error_text[:100]}"
    log_action("self_improvement", f"Ищу решение: {search_query}", "info")
    
    results = search_web(search_query, 2)
    if not results:
        log_action("self_improvement", "Решений не найдено", "warning")
        return
    
    solutions = []
    for result in results:
        content = get_page_content(result["url"])
        if content:
            solutions.append(content[:1000])
    
    if solutions:
        log_action("self_improvement", f"Найдено {len(solutions)} решений", "success")
        log_action("solution_example", solutions[0][:300], "info")

def start_self_improvement_loop():
    """Запускает цикл самообучения раз в час"""
    def loop():
        while True:
            time.sleep(3600)
            try:
                log_action("auto_improve", "Автоматический цикл самообучения", "info")
                research_and_improve()
            except Exception as e:
                log_action("auto_improve_error", str(e), "error")
    
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    log_action("self_improvement", "Фоновое самообучение запущено", "success")

# Запускаем фоновое самообучение
start_self_improvement_loop()

# ===== КОМАНДЫ =====
@bot.message_handler(commands=['start', 'help'])
def menu_command(message):
    log_action("menu", f"user={message.from_user.id}", "info")
    bot.reply_to(message, "📋 МЕНЮ БОТА\n\n/ai [вопрос] - спросить ИИ\n/status_full - полный статус\n/evolve - запустить самообучение\n/search [запрос] - поиск в интернете\n/read [url] - прочитать страницу\n/logs - показать последние логи")

@bot.message_handler(commands=['ai'])
def ai_command(message):
    user_text = message.text.replace('/ai', '').strip()
    if not user_text:
        bot.reply_to(message, "/ai [вопрос]")
        return
    
    log_action("ai", f"user={message.from_user.id} запрос: {user_text[:50]}", "info")
    status_msg = bot.reply_to(message, "🤔 Думаю...")
    
    if not OPENROUTER_API_KEY:
        log_action("ai_error", "OpenRouter key not set", "error")
        bot.edit_message_text("OpenRouter key not set", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    try:
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "openrouter/free",
            "messages": [{"role": "user", "content": user_text}],
            "max_tokens": 500
        }
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
        
        if r.status_code == 200:
            answer = r.json()["choices"][0]["message"]["content"]
            bot.edit_message_text(answer, chat_id=message.chat.id, message_id=status_msg.message_id)
            log_action("ai_response", f"ответ отправлен", "success")
        else:
            log_action("ai_api_error", f"status {r.status_code}", "error")
            bot.edit_message_text(f"API error: {r.status_code}", chat_id=message.chat.id, message_id=status_msg.message_id)
    except Exception as e:
        log_action("ai_exception", str(e), "error")
        bot.edit_message_text(f"Error: {e}", chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['evolve'])
def evolve_command(message):
    """Запускает процесс самообучения вручную"""
    log_action("evolve", f"user={message.from_user.id} запустил самообучение", "info")
    status_msg = bot.reply_to(message, "🧬 Агент начал самоанализ и поиск улучшений...")
    
    def do_research():
        research_and_improve()
        bot.edit_message_text("✅ Цикл самообучения завершён", 
                              chat_id=message.chat.id, message_id=status_msg.message_id)
        log_action("evolve_complete", "самообучение завершено", "success")
    
    thread = threading.Thread(target=do_research, daemon=True)
    thread.start()

@bot.message_handler(commands=['search'])
def search_command(message):
    query = message.text.replace('/search', '').strip()
    if not query:
        bot.reply_to(message, "/search [запрос]\nПример: /search как работает ИИ")
        return
    
    log_action("search", f"user={message.from_user.id} поиск: {query}", "info")
    status_msg = bot.reply_to(message, f"🔍 Ищу: {query}")
    
    results = search_web(query, 5)
    if not results:
        log_action("search_no_results", query, "warning")
        bot.edit_message_text("❌ Ничего не найдено", chat_id=message.chat.id, message_id=status_msg.message_id)
        return
    
    response = f"🔍 РЕЗУЛЬТАТЫ ПОИСКА: {query}\n\n"
    for i, r in enumerate(results, 1):
        response += f"{i}. {r['title']}\n{r['url']}\n\n"
    
    bot.edit_message_text(response[:4000], chat_id=message.chat.id, message_id=status_msg.message_id)
    log_action("search_success", f"найдено {len(results)} результатов", "success")

@bot.message_handler(commands=['read'])
def read_command(message):
    url = message.text.replace('/read', '').strip()
    if not url:
        bot.reply_to(message, "/read [url]\nПример: /read https://example.com")
        return
    
    if not url.startswith('http'):
        url = 'https://' + url
    
    log_action("read", f"user={message.from_user.id} читает {url}", "info")
    status_msg = bot.reply_to(message, f"📖 Читаю: {url}")
    
    content = get_page_content(url)
    if content:
        bot.edit_message_text(f"📄 СОДЕРЖИМОЕ:\n\n{content[:3000]}", 
                              chat_id=message.chat.id, message_id=status_msg.message_id)
        log_action("read_success", f"прочитано {len(content)} символов", "success")
    else:
        log_action("read_error", f"не удалось прочитать {url}", "error")
        bot.edit_message_text("❌ Не удалось прочитать страницу", 
                              chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['logs'])
def logs_command(message):
    """Показывает последние логи в чате"""
    log_action("logs", f"user={message.from_user.id} запросил логи", "info")
    
    try:
        with open("agent_actions.log", "r") as f:
            lines = f.readlines()
        
        if not lines:
            bot.reply_to(message, "📭 Логов пока нет")
            return
        
        # Берём последние 20 строк
        last_logs = lines[-20:]
        
        response = "📋 ПОСЛЕДНИЕ ЛОГИ:\n\n"
        for line in last_logs:
            try:
                log = json.loads(line)
                emoji = "✅" if log.get("status") == "success" else "🔴" if log.get("status") == "error" else "ℹ️"
                response += f"{emoji} {log.get('timestamp', '')} {log.get('action', '')}\n"
            except:
                response += f"• {line[:100]}\n"
        
        bot.reply_to(message, response[:4000])
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка чтения логов: {e}")

# ===== ВЕБХУК =====
@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
        bot.process_new_updates([update])
        return 'ok', 200
    except Exception as e:
        log_action("webhook_error", str(e), "error")
        return 'error', 500

@app.route('/health')
def health():
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    url = os.environ.get('RENDER_EXTERNAL_URL', f"http://localhost:{port}")
    bot.remove_webhook()
    bot.set_webhook(url=f"{url}/{TELEGRAM_TOKEN}")
    log_action("bot_start", "Бот запущен", "success")
    app.run(host='0.0.0.0', port=port)
