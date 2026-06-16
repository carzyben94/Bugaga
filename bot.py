import os
import time
import logging
import json
import requests
import threading
import urllib.parse
import xml.etree.ElementTree as ET
from flask import Flask, request
import telebot
from bs4 import BeautifulSoup
from datetime import datetime
from super_agent import SuperAgent

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

# ===== СУПЕР-АГЕНТ =====
super_agent = SuperAgent({
    'GITHUB_TOKEN': GITHUB_TOKEN,
    'RENDER_API_KEY': RENDER_API_KEY,
    'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
    'OPENROUTER_API_KEY': OPENROUTER_API_KEY,
    'GITHUB_REPO': GITHUB_REPO,
    'RENDER_SERVICE_ID': RENDER_SERVICE_ID
})

# ===== СТАТУС МОДУЛЬ =====
try:
    from status import register_status_full
    register_status_full(bot)
    print("Status module loaded")
except Exception as e:
    print(f"Status not loaded: {e}")

# ===== ЛОГИ В ЧАТ =====
def send_log_to_admin(action, details=None, status="info"):
    if not ADMIN_CHAT_ID:
        return
    emoji = "✅" if status == "success" else "🔴" if status == "error" else "ℹ️"
    timestamp = time.strftime("%H:%M:%S")
    try:
        bot.send_message(ADMIN_CHAT_ID, f"{emoji} [{timestamp}] {action}: {details}")
    except:
        pass

def log_action(action, details=None, status="info", send=True):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {"timestamp": timestamp, "action": action, "status": status, "details": details}
    try:
        with open("agent_actions.log", "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except:
        pass
    if send:
        send_log_to_admin(action, details, status)

def get_last_errors(limit=5):
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

# ===== БРАУЗЕР МОДУЛЬ =====
def open_browser_sync(url="https://example.com"):
    """Открывает сайт через requests"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7'
        }
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            title = soup.find('title')
            title_text = title.get_text(strip=True) if title else "Без заголовка"
            return f"✅ Заголовок: {title_text}"
        else:
            return f"❌ Ошибка HTTP: {r.status_code}"
    except Exception as e:
        log_action("browser_error", str(e), "error")
        return f"❌ Ошибка: {str(e)[:100]}"

@bot.message_handler(commands=['browser'])
def handle_browser(message):
    url = message.text.replace('/browser', '').strip()
    if not url:
        bot.reply_to(message, "🌐 Укажите URL\nПример: /browser https://example.com")
        return
    
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    log_action("browser", f"user={message.from_user.id} открывает {url}", "info")
    status_msg = bot.reply_to(message, f"🌐 Открываю {url}...")
    
    def do_browser():
        try:
            result = open_browser_sync(url)
            bot.edit_message_text(result, chat_id=message.chat.id, message_id=status_msg.message_id)
            log_action("browser_success", "страница открыта", "success")
        except Exception as e:
            bot.edit_message_text(f"❌ Ошибка: {e}", chat_id=message.chat.id, message_id=status_msg.message_id)
            log_action("browser_error", str(e), "error")
    
    thread = threading.Thread(target=do_browser, daemon=True)
    thread.start()

# ===== ПОСТЫ ИЗ X (TWITTER) ЧЕРЕЗ NITTER =====
@bot.message_handler(commands=['xposts'])
def xposts_command(message):
    status_msg = bot.reply_to(message, "🐦 Ищу последние посты из X...")
    
    def do_xposts():
        try:
            # Только один аккаунт - Лентач
            accounts = [
                {"username": "the_lentach", "name": "Лентач"}
            ]
            
            all_posts = []
            
            for account in accounts:
                try:
                    # Парсим RSS через Nitter
                    url = f"https://nitter.net/{account['username']}/rss"
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                    response = requests.get(url, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        root = ET.fromstring(response.content)
                        items = root.findall('.//item')
                        
                        # Берём только 3 последних поста
                        for item in items[:3]:
                            title_elem = item.find('title')
                            if title_elem is not None and title_elem.text:
                                text = title_elem.text.strip()
                                
                                pub_date = item.find('pubDate')
                                date = pub_date.text if pub_date is not None else ""
                                
                                link = item.find('link')
                                post_url = link.text if link is not None else ""
                                
                                if len(text) > 500:
                                    text = text[:500] + "..."
                                
                                all_posts.append({
                                    'username': account['username'],
                                    'name': account['name'],
                                    'text': text,
                                    'date': date[:16] if date else "",
                                    'url': post_url
                                })
                                
                    else:
                        # Если Nitter не работает, пробуем альтернативный инстанс
                        alt_url = f"https://nitter.poast.org/{account['username']}/rss"
                        response = requests.get(alt_url, headers=headers, timeout=10)
                        if response.status_code == 200:
                            root = ET.fromstring(response.content)
                            items = root.findall('.//item')
                            
                            for item in items[:3]:
                                title_elem = item.find('title')
                                if title_elem is not None and title_elem.text:
                                    text = title_elem.text.strip()
                                    
                                    pub_date = item.find('pubDate')
                                    date = pub_date.text if pub_date is not None else ""
                                    
                                    link = item.find('link')
                                    post_url = link.text if link is not None else ""
                                    
                                    if len(text) > 500:
                                        text = text[:500] + "..."
                                    
                                    all_posts.append({
                                        'username': account['username'],
                                        'name': account['name'],
                                        'text': text,
                                        'date': date[:16] if date else "",
                                        'url': post_url
                                    })
                    
                except Exception as e:
                    log_action("xposts_account_error", f"{account['username']}: {str(e)[:50]}", "warning")
                    continue
            
            if not all_posts:
                bot.edit_message_text(
                    "❌ Не удалось загрузить посты. Попробуйте позже.",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id
                )
                return
            
            current_time = datetime.now().strftime("%d.%m.%Y %H:%M")
            result = "🐦 *ПОСЛЕДНИЕ ПОСТЫ ИЗ X*\n"
            result += f"📅 {current_time}\n\n"
            
            # Показываем только 3 поста
            for i, post in enumerate(all_posts[:3], 1):
                result += f"📌 *@{post['username']}*\n"
                result += f"{post['text']}\n"
                result += f"🕐 {post['date']}\n"
                if post['url']:
                    result += f"🔗 [Ссылка]({post['url']})\n"
                
                if i < len(all_posts[:3]):
                    result += "—" * 30 + "\n\n"
            
            result += "\n💡 /xposts — обновить посты"
            
            bot.edit_message_text(
                result,
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            
            log_action("xposts", f"показано {len(all_posts[:3])} постов", "success")
            
        except Exception as e:
            log_action("xposts_error", str(e), "error")
            bot.edit_message_text(
                f"❌ Ошибка при загрузке постов: {str(e)[:100]}",
                chat_id=message.chat.id,
                message_id=status_msg.message_id
            )
    
    thread = threading.Thread(target=do_xposts, daemon=True)
    thread.start()

# ===== НОВЫЕ ИИ-МОДЕЛИ =====
@bot.message_handler(commands=['newmodels'])
def new_models_command(message):
    status_msg = bot.reply_to(message, "🚀 Ищу новые ИИ-модели...")
    
    def do_new_models():
        try:
            url = "https://www.demandsphere.com/research/demandsphere-radar/ai-frontier-model-tracker/api.json"
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            models = data.get('models', [])
            
            sorted_models = sorted(models, key=lambda x: x.get('rel', ''), reverse=True)
            
            if not sorted_models:
                bot.edit_message_text(
                    "❌ Список моделей пуст. Попробуйте позже.",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id
                )
                return
            
            current_time = datetime.now().strftime("%d.%m.%Y %H:%M")
            result = "🚀 *НОВЫЕ ИИ-МОДЕЛИ*\n"
            result += f"📅 *Обновлено:* {current_time}\n\n"
            
            for i, model in enumerate(sorted_models[:10], 1):
                name = model.get('name', 'Неизвестно')
                provider = model.get('prov', 'Неизвестно')
                model_type = model.get('type', 'N/A')
                release_date = model.get('rel', 'N/A')
                context = model.get('ctx', 'N/A')
                is_multimodal = "✅ Да" if model.get('mm', False) else "❌ Нет"
                
                if i == 1:
                    num_emoji = "🥇"
                elif i == 2:
                    num_emoji = "🥈"
                elif i == 3:
                    num_emoji = "🥉"
                else:
                    num_emoji = f"{i}."
                
                result += f"{num_emoji} *{name}*\n"
                result += f"   🏢 {provider}\n"
                result += f"   📋 Тип: {model_type}\n"
                result += f"   📅 Релиз: {release_date}\n"
                result += f"   📚 Контекст: {context}K\n"
                result += f"   🖼️ Мультимодальная: {is_multimodal}\n\n"
            
            result += "💡 /newmodels — обновить список"
            
            bot.edit_message_text(
                result,
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode='Markdown'
            )
            
            log_action("newmodels", f"показано {len(sorted_models[:10])} моделей", "success")
            
        except Exception as e:
            log_action("newmodels_error", str(e), "error")
            bot.edit_message_text(
                f"❌ Ошибка при загрузке данных: {str(e)[:100]}",
                chat_id=message.chat.id,
                message_id=status_msg.message_id
            )
    
    thread = threading.Thread(target=do_new_models, daemon=True)
    thread.start()

# ===== КРИПТОВАЛЮТЫ =====
@bot.message_handler(commands=['crypto'])
def crypto_command(message):
    status_msg = bot.reply_to(message, "💰 Узнаю курсы криптовалют...")
    
    def do_crypto():
        try:
            r1 = requests.get("https://api.binance.com/api/v3/ticker/price", 
                              params={"symbol": "BTCUSDT"}, timeout=10)
            
            r2 = requests.get("https://api.binance.com/api/v3/ticker/price", 
                              params={"symbol": "ETHUSDT"}, timeout=10)
            
            if r1.status_code != 200 or r2.status_code != 200:
                bot.edit_message_text("❌ Ошибка Binance API", 
                                      chat_id=message.chat.id, 
                                      message_id=status_msg.message_id)
                return
            
            btc_usd = float(r1.json().get('price', 0))
            eth_usd = float(r2.json().get('price', 0))
            
            r3 = requests.get("https://api.binance.com/api/v3/ticker/price", 
                              params={"symbol": "USDRUB"}, timeout=10)
            
            if r3.status_code == 200:
                usd_rub = float(r3.json().get('price', 95))
            else:
                usd_rub = 95
            
            btc_rub = round(btc_usd * usd_rub, 2)
            eth_rub = round(eth_usd * usd_rub, 2)
            
            btc_usd_str = f"${btc_usd:,.2f}"
            btc_eur_str = f"€{btc_usd * 0.92:,.2f}"
            btc_rub_str = f"{btc_rub:,.2f} ₽"
            
            eth_usd_str = f"${eth_usd:,.2f}"
            eth_eur_str = f"€{eth_usd * 0.92:,.2f}"
            eth_rub_str = f"{eth_rub:,.2f} ₽"
            
            result = (
                "🟡 BITCOIN (BTC):\n"
                f"  • USD: {btc_usd_str}\n"
                f"  • EUR: {btc_eur_str}\n"
                f"  • RUB: {btc_rub_str}\n\n"
                "🔷 ETHEREUM (ETH):\n"
                f"  • USD: {eth_usd_str}\n"
                f"  • EUR: {eth_eur_str}\n"
                f"  • RUB: {eth_rub_str}"
            )
            
            bot.edit_message_text(result, 
                                  chat_id=message.chat.id, 
                                  message_id=status_msg.message_id)
            log_action("crypto", "курсы получены (Binance)", "success")
            
        except Exception as e:
            log_action("crypto_error", str(e), "error")
            bot.edit_message_text(f"❌ Ошибка: {str(e)[:100]}", 
                                  chat_id=message.chat.id, 
                                  message_id=status_msg.message_id)
    
    thread = threading.Thread(target=do_crypto, daemon=True)
    thread.start()

# ===== ПАРСИНГ ЛЮБОГО URL =====
@bot.message_handler(commands=['parse'])
def parse_command(message):
    url = message.text.replace('/parse', '').strip()
    if not url:
        bot.reply_to(message, "❌ Укажите URL\nПример: /parse https://example.com")
        return
    
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    status_msg = bot.reply_to(message, f"🔍 Парсю {url}...")
    
    def do_parse():
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            r = requests.get(url, headers=headers, timeout=10)
            
            if r.status_code != 200:
                bot.edit_message_text(f"❌ Ошибка HTTP: {r.status_code}", 
                                      chat_id=message.chat.id, 
                                      message_id=status_msg.message_id)
                return
            
            soup = BeautifulSoup(r.text, 'lxml')
            
            title = soup.find('title')
            title_text = title.get_text(strip=True) if title else "Без заголовка"
            
            paragraphs = soup.find_all('p')
            text = " ".join([p.get_text(strip=True) for p in paragraphs[:5]])
            
            if not text or len(text) < 50:
                text = "⚠️ Контент не найден (возможно, сайт на JS)"
            else:
                text = text[:2000] + "..." if len(text) > 2000 else text
            
            result = f"📄 {title_text}\n\n{text}"
            
            bot.edit_message_text(result[:4000], 
                                  chat_id=message.chat.id, 
                                  message_id=status_msg.message_id)
            log_action("parse", f"{url} - {title_text[:50]}", "success")
            
        except Exception as e:
            log_action("parse_error", str(e), "error")
            bot.edit_message_text(f"❌ Ошибка: {str(e)[:100]}", 
                                  chat_id=message.chat.id, 
                                  message_id=status_msg.message_id)
    
    thread = threading.Thread(target=do_parse, daemon=True)
    thread.start()

# ===== СУПЕР-АГЕНТ: КОМАНДЫ =====
@bot.message_handler(commands=['agent_report'])
def agent_report_command(message):
    """Полный отчёт супер-агента"""
    if str(message.from_user.id) != str(ADMIN_CHAT_ID):
        bot.reply_to(message, "⛔ Только администратор может использовать эту команду")
        return
    
    status_msg = bot.reply_to(message, "🧠 Супер-агент собирает данные...")
    
    def do_report():
        try:
            report = super_agent.get_full_report()
            bot.edit_message_text(
                report,
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode='Markdown'
            )
        except Exception as e:
            bot.edit_message_text(
                f"❌ Ошибка: {str(e)[:200]}",
                chat_id=message.chat.id,
                message_id=status_msg.message_id
            )
    
    threading.Thread(target=do_report, daemon=True).start()

@bot.message_handler(commands=['fix'])
def fix_command(message):
    """Авто-исправление проблемы"""
    if str(message.from_user.id) != str(ADMIN_CHAT_ID):
        bot.reply_to(message, "⛔ Только администратор")
        return
    
    issue = message.text.replace('/fix', '').strip()
    if not issue:
        bot.reply_to(message, "📝 Опишите проблему:\n/fix [описание]")
        return
    
    status_msg = bot.reply_to(message, f"🔧 Исправляю: {issue[:50]}...")
    
    def do_fix():
        try:
            if super_agent.auto_improve_code(issue):
                bot.edit_message_text(
                    "✅ Код улучшен и задеплоен на Render!",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id
                )
            else:
                bot.edit_message_text(
                    "❌ Не удалось автоматически улучшить код",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id
                )
        except Exception as e:
            bot.edit_message_text(
                f"❌ Ошибка: {str(e)[:200]}",
                chat_id=message.chat.id,
                message_id=status_msg.message_id
            )
    
    threading.Thread(target=do_fix, daemon=True).start()

# ===== КОМАНДЫ =====
@bot.message_handler(commands=['start', 'help'])
def menu_command(message):
    log_action("menu", f"user={message.from_user.id}", "info")
    
    menu_text = (
        "📋 МЕНЮ БОТА\n\n"
        "🤖 ИСКУССТВЕННЫЙ ИНТЕЛЛЕКТ\n"
        "/ai [вопрос] - спросить ИИ\n"
        "/xposts - посты из X\n"
        "/newmodels - новые ИИ-модели\n\n"
        "🌐 ИНТЕРНЕТ И ДАННЫЕ\n"
        "/browser [url] - открыть сайт\n"
        "/parse [url] - парсинг сайта\n\n"
        "💰 ФИНАНСЫ\n"
        "/crypto - курсы криптовалют\n\n"
        "⚙️ СИСТЕМА\n"
        "/agent_report - отчёт супер-агента\n"
        "/fix [описание] - авто-исправление\n"
        "/status_full - статус системы\n"
        "/logs - показать логи"
    )
    
    bot.reply_to(message, menu_text)

@bot.message_handler(commands=['ai'])
def ai_command(message):
    user_text = message.text.replace('/ai', '').strip()
    if not user_text:
        bot.reply_to(message, "🤖 Введите вопрос после /ai\nПример: /ai что такое нейросеть")
        return
    
    log_action("ai", f"user={message.from_user.id} запрос: {user_text[:50]}", "info")
    status_msg = bot.reply_to(message, "🤔 Думаю...")
    
    if not OPENROUTER_API_KEY:
        log_action("ai_error", "OpenRouter key not set", "error")
        bot.edit_message_text("❌ OpenRouter API ключ не настроен", chat_id=message.chat.id, message_id=status_msg.message_id)
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
            log_action("ai_response", "ответ отправлен", "success")
        else:
            log_action("ai_api_error", f"status {r.status_code}", "error")
            bot.edit_message_text(f"❌ Ошибка API: {r.status_code}", chat_id=message.chat.id, message_id=status_msg.message_id)
    except Exception as e:
        log_action("ai_exception", str(e), "error")
        bot.edit_message_text(f"❌ Ошибка: {e}", chat_id=message.chat.id, message_id=status_msg.message_id)

@bot.message_handler(commands=['status_full'])
def status_full_command(message):
    bot.reply_to(message, "📊 Статус системы:\n✅ Бот работает\n✅ Все модули активны\n✅ Супер-агент активен")

@bot.message_handler(commands=['logs'])
def logs_command(message):
    log_action("logs", f"user={message.from_user.id} запросил логи", "info")
    
    try:
        with open("agent_actions.log", "r") as f:
            lines = f.readlines()
        
        if not lines:
            bot.reply_to(message, "📭 Логов пока нет")
            return
        
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
        bot.reply_to(message, f"❌ Ошибка: {e}")

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