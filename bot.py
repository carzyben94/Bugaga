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

# ===== БРАУЗЕР МОДУЛЬ (через requests) =====
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
        url = "https://example.com"
    
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

# ===== ПАРСИНГ НОВОСТЕЙ (DW и BBC на русском) =====
@bot.message_handler(commands=['news'])
def news_command(message):
    status_msg = bot.reply_to(message, "📰 Ищу последние новости...")
    
    def do_news():
        try:
            # Новые источники: DW и BBC на русском
            rss_sources = [
                "https://rss.dw.com/rdf/rss-ru-all",  # DW на русском
                "https://www.bbc.com/russian/index.xml"  # BBC на русском
            ]
            
            result = "📰 ПОСЛЕДНИЕ НОВОСТИ:\n\n"
            count = 0
            used_titles = set()  # Для удаления дубликатов
            
            for rss_url in rss_sources:
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Accept': 'application/rss+xml, application/xml, text/xml'
                    }
                    r = requests.get(rss_url, headers=headers, timeout=15)
                    
                    if r.status_code == 200:
                        # Пробуем парсить RSS
                        try:
                            root = ET.fromstring(r.content)
                            items = root.findall('.//item')
                            
                            if not items:
                                items = root.findall('.//entry')
                            
                            if items:
                                for item in items[:10]:
                                    title_elem = item.find('title')
                                    if title_elem is not None and title_elem.text:
                                        text = title_elem.text.strip()
                                        # Очищаем от CDATA
                                        text = text.replace('<![CDATA[', '').replace(']]>', '')
                                        # Очищаем от HTML тегов
                                        text = BeautifulSoup(text, 'html.parser').get_text()
                                        
                                        if text and len(text) > 10 and len(text) < 500:
                                            # Проверяем на дубликаты
                                            if text not in used_titles:
                                                used_titles.add(text)
                                                count += 1
                                                source = "DW" if "dw.com" in rss_url else "BBC"
                                                result += f"{count}. {text} ({source})\n"
                                            
                                            if count >= 15:
                                                break
                        except ET.ParseError:
                            # Если не RSS, пробуем парсить HTML
                            soup = BeautifulSoup(r.text, 'lxml')
                            titles = soup.find_all(['h1', 'h2', 'h3', 'a'])
                            for title in titles[:20]:
                                text = title.get_text(strip=True)
                                if text and len(text) > 20 and len(text) < 300:
                                    if text not in used_titles:
                                        used_titles.add(text)
                                        count += 1
                                        source = "DW" if "dw.com" in rss_url else "BBC"
                                        result += f"{count}. {text} ({source})\n"
                                    
                                    if count >= 15:
                                        break
                    
                except Exception as e:
                    log_action("news_source_error", f"{rss_url}: {str(e)[:50]}", "warning")
                    continue
                
                if count >= 15:
                    break
            
            if count == 0:
                # Если RSS не сработал, пробуем парсить HTML напрямую
                result = get_news_from_html()
            
            if count == 0 and result == "📰 ПОСЛЕДНИЕ НОВОСТИ:\n\n":
                result = "❌ Новостей не найдено. Попробуйте позже."
            
            bot.edit_message_text(result[:4000], 
                                  chat_id=message.chat.id, 
                                  message_id=status_msg.message_id)
            log_action("news", f"найдено {count} новостей", "success" if count > 0 else "warning")
            
        except Exception as e:
            log_action("news_error", str(e), "error")
            bot.edit_message_text(f"❌ Ошибка: {str(e)[:100]}", 
                                  chat_id=message.chat.id, 
                                  message_id=status_msg.message_id)
    
    thread = threading.Thread(target=do_news, daemon=True)
    thread.start()

def get_news_from_html():
    """Запасной способ: парсинг HTML напрямую с DW и BBC"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'ru-RU,ru;q=0.9'
        }
        
        result = "📰 ПОСЛЕДНИЕ НОВОСТИ:\n\n"
        count = 0
        used_titles = set()
        
        # Пробуем DW
        try:
            r = requests.get("https://www.dw.com/ru/top-stories/s-9097", headers=headers, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'lxml')
                # Ищем заголовки статей
                for selector in ['h2 a', '.teaser__headline a', 'article h2 a', '.news-item h2 a']:
                    titles = soup.select(selector)
                    if titles:
                        for title in titles[:10]:
                            text = title.get_text(strip=True)
                            if text and len(text) > 20 and len(text) < 300 and text not in used_titles:
                                used_titles.add(text)
                                count += 1
                                result += f"{count}. {text} (DW)\n"
                        break
        except:
            pass
        
        # Пробуем BBC
        try:
            r = requests.get("https://www.bbc.com/russian", headers=headers, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'lxml')
                for selector in ['h2 a', '.gs-c-promo-heading', 'article a', '.bbc-news__title a']:
                    titles = soup.select(selector)
                    if titles:
                        for title in titles[:10]:
                            text = title.get_text(strip=True)
                            if text and len(text) > 20 and len(text) < 300 and text not in used_titles:
                                used_titles.add(text)
                                count += 1
                                result += f"{count}. {text} (BBC)\n"
                        break
        except:
            pass
        
        if count == 0:
            return "❌ Новостей не найдено"
        
        return result
    except Exception as e:
        log_action("news_html_error", str(e), "error")
        return "❌ Новостей не найдено"

# ===== КРИПТОВАЛЮТЫ (Binance) =====
@bot.message_handler(commands=['crypto'])
def crypto_command(message):
    status_msg = bot.reply_to(message, "💰 Узнаю курсы криптовалют...")
    
    def do_crypto():
        try:
            # Получаем BTC/USDT
            r1 = requests.get("https://api.binance.com/api/v3/ticker/price", 
                              params={"symbol": "BTCUSDT"}, timeout=10)
            
            # Получаем ETH/USDT
            r2 = requests.get("https://api.binance.com/api/v3/ticker/price", 
                              params={"symbol": "ETHUSDT"}, timeout=10)
            
            if r1.status_code != 200 or r2.status_code != 200:
                bot.edit_message_text("❌ Ошибка Binance API", 
                                      chat_id=message.chat.id, 
                                      message_id=status_msg.message_id)
                return
            
            btc_usd = float(r1.json().get('price', 0))
            eth_usd = float(r2.json().get('price', 0))
            
            # Получаем курс USD/RUB
            r3 = requests.get("https://api.binance.com/api/v3/ticker/price", 
                              params={"symbol": "USDRUB"}, timeout=10)
            
            if r3.status_code == 200:
                usd_rub = float(r3.json().get('price', 95))
            else:
                usd_rub = 95
            
            # Конвертируем в рубли
            btc_rub = round(btc_usd * usd_rub, 2)
            eth_rub = round(eth_usd * usd_rub, 2)
            
            # Форматируем с разделителями тысяч
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

# ===== КОМАНДЫ =====
@bot.message_handler(commands=['start', 'help'])
def menu_command(message):
    log_action("menu", f"user={message.from_user.id}", "info")
    bot.reply_to(message, 
        "📋 МЕНЮ БОТА\n\n"
        "/ai [вопрос] - спросить ИИ\n"
        "/status_full - полный статус\n"
        "/browser [url] - открыть сайт в браузере\n"
        "/news - последние новости (DW, BBC)\n"
        "/crypto - курсы Bitcoin и Ethereum\n"
        "/parse [url] - парсинг любого сайта\n"
        "/logs - показать логи"
    )

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
            log_action("ai_response", "ответ отправлен", "success")
        else:
            log_action("ai_api_error", f"status {r.status_code}", "error")
            bot.edit_message_text(f"API error: {r.status_code}", chat_id=message.chat.id, message_id=status_msg.message_id)
    except Exception as e:
        log_action("ai_exception", str(e), "error")
        bot.edit_message_text(f"Error: {e}", chat_id=message.chat.id, message_id=status_msg.message_id)

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