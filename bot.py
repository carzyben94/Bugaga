# bot.py 
import os
import time
import logging
import json
from flask import Flask, request
import telebot

from xposts import register_xposts
from crypto import register_crypto
from ai import register_ai
from browser_ai import register_browser_ai
from crawler_ai import register_crawler_ai
from render import register_render
from github import register_github

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
RENDER_API_KEY = os.environ.get("RENDER_API_KEY")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "carzyben94/Bugaga")
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not set")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# ===== РЕГИСТРАЦИЯ МОДУЛЕЙ =====
modules = [
    ("xposts", register_xposts, []),
    ("crypto", register_crypto, []),
    ("ai", register_ai, [AGNES_API_KEY]),
    ("browser_ai", register_browser_ai, [AGNES_API_KEY]),
    ("crawler_ai", register_crawler_ai, [AGNES_API_KEY]),
    ("render", register_render, []),
    ("github", register_github, []),
]

for name, register_func, args in modules:
    try:
        register_func(bot, *args)
    except TypeError:
        try:
            register_func(bot)
        except Exception as e:
            print(f"{name} error: {e}")
    except Exception as e:
        print(f"{name} error: {e}")

# ===== ЛОГИ =====
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

# ===== ОБЩЕЕ МЕНЮ =====
MENU_TEXT = (
    "🤖 <b>BUGAGA BOT</b>\n"
    "Твой агент для ИИ, новостей и крипты\n\n"
    
    "🧠 <b>Искусственный интеллект</b>\n"
    "  ├ /ai — Задать вопрос ИИ\n"
    "  ├ /browser_ai — ИИ читает сайт\n"
    "  └ /crawler_ai — Собрать новости\n\n"
    
    "📰 <b>Новости</b>\n"
    "  └ /xposts — Посты из X\n\n"
    
    "💰 <b>Финансы</b>\n"
    "  └ /crypto — Курсы BTC и ETH\n\n"
    
    "🔧 <b>Render</b>\n"
    "  ├ /render_list — Список сервисов (найди ID)\n"
    "  ├ /render_status — Статус сервиса\n"
    "  ├ /render_restart — Перезапустить\n"
    "  ├ /render_env — Переменные окружения\n"
    "  └ /render_logs — Логи (Dashboard)\n\n"
    
    "💾 <b>GitHub</b>\n"
    "  ├ /gh_list [путь] — Список файлов\n"
    "  ├ /gh_read [путь] — Прочитать файл\n"
    "  ├ /gh_write [путь] [текст] — Записать файл\n"
    "  ├ /gh_del [путь] — Удалить файл\n"
    "  ├ /gh_commits [N] — Коммиты\n"
    "  ├ /gh_branches — Ветки\n"
    "  └ /gh_repo — Инфо о репо"
)

@bot.message_handler(commands=["start", "help"])
def menu_command(message):
    try:
        log_action(message.text.lstrip("/"), f"user={message.from_user.id}", "info")
        bot.reply_to(message, MENU_TEXT, parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")

# ===== ТЕСТОВАЯ КОМАНДА =====
@bot.message_handler(commands=["test"])
def test_command(message):
    bot.reply_to(message, "✅ Бот работает!")

# ===== ВЕБХУК =====
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
        bot.process_new_updates([update])
        return "ok", 200
    except Exception as e:
        print(f"webhook error: {e}")
        return "error", 500

@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    url = os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{port}")
    
    print("🔄 Удаляю старый webhook...")
    try:
        bot.remove_webhook()
        time.sleep(2)
    except Exception as e:
        print(f"remove webhook error: {e}")
    
    print(f"🔄 Устанавливаю webhook: {url}/{TELEGRAM_TOKEN}")
    try:
        bot.set_webhook(url=f"{url}/{TELEGRAM_TOKEN}")
        print("✅ Webhook установлен!")
    except Exception as e:
        print(f"set webhook error: {e}")
    
    try:
        info = bot.get_webhook_info()
        print(f"📊 Webhook info: {info}")
    except Exception as e:
        print(f"get webhook info error: {e}")
    
    log_action("bot_start", "Бот запущен", "success")
    app.run(host="0.0.0.0", port=port)
