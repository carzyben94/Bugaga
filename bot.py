# bot.py 
import os
import sys
import time
import logging
import json
from flask import Flask, request
import telebot

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xposts import register_xposts
from crypto import register_crypto
from ai import register_ai
from browser_ai import register_browser_ai
from crawler_ai import register_crawler_ai
from render import register_render
from github import register_github
from xx import register_x_play

# === SELENIUM X AGENT ===
SELENIUM_AVAILABLE = False
register_selenium_bot = None
get_full_status = None
get_auth_info = None
AGENT_READY = None

print("[DEBUG] Пытаюсь импортировать selenium_x_agent...", flush=True)
try:
    from selenium_x_agent import register_selenium_bot as _rsb, get_full_status as _gfs, get_auth_info as _gai, AGENT_READY as _ar
    register_selenium_bot = _rsb
    get_full_status = _gfs
    get_auth_info = _gai
    AGENT_READY = _ar
    SELENIUM_AVAILABLE = True
    print("[DEBUG] Selenium module imported УСПЕШНО", flush=True)
except Exception as e:
    print(f"[DEBUG] Selenium module not available: {e}", flush=True)
    import traceback
    traceback.print_exc()

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
    ("xx", register_x_play, []),
]

for name, register_func, args in modules:
    try:
        register_func(bot, *args)
        print(f"[DEBUG] Module {name} OK")
    except TypeError:
        try:
            register_func(bot)
            print(f"[DEBUG] Module {name} OK (no args)")
        except Exception as e:
            print(f"[DEBUG] {name} error: {e}")
    except Exception as e:
        print(f"[DEBUG] {name} error: {e}")

# === РЕГИСТРАЦИЯ SELENIUM ===
if SELENIUM_AVAILABLE and register_selenium_bot:
    try:
        print("[DEBUG] Регистрирую selenium бота...", flush=True)
        register_selenium_bot(bot)
        print("[DEBUG] Module selenium_x_agent OK", flush=True)
    except Exception as e:
        print(f"[DEBUG] selenium_x_agent error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        SELENIUM_AVAILABLE = False

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


def get_selenium_status_line():
    """Получить строку статуса Selenium для меню — ДИНАМИЧЕСКИ"""
    if not SELENIUM_AVAILABLE:
        return "  ⚠️ <i>модуль не загружен</i>\n"
    try:
        status = get_full_status()
        ready = status.get("agent_ready", False)
        auth = status.get("auth_info")
        
        if auth:
            auth_line = f"  👤 <code>@{auth['username']}</code>\n"
        else:
            auth_line = "  👤 <i>не подключён</i>\n"
        
        icon = "🟢" if ready else "🔴"
        ver = status.get("selenium_pip", {}).get("version", "?")
        return f"  {icon} pip v{ver} |\n{auth_line}"
    except Exception as e:
        print(f"[DEBUG] get_selenium_status_line error: {e}", flush=True)
        return "  ⚠️ <i>ошибка статуса</i>\n"


def build_menu_text():
    """СТРОИТ МЕНЮ ДИНАМИЧЕСКИ — при каждом вызове /start"""
    return (
        "🤖 <b>BUGAGA BOT</b>\n"
        "Твой агент для ИИ, новостей и крипты\n\n"
        
        "🧠 <b>Искусственный интеллект</b>\n"
        "  ├ /ai — Задать вопрос ИИ\n"
        "  ├ /browser_ai — ИИ читает сайт\n"
        "  └ /crawler_ai — Собрать новости\n\n"
        
        "📰 <b>Новости</b>\n"
        "  ├ /xposts — Посты из X (RSS)\n"
        "  └ /x_timeline [user] — Лента X (Playwright)\n\n"
        
        "💰 <b>Финансы</b>\n"
        "  └ /crypto — Курсы BTC и ETH\n\n"
        
        "🔧 <b>Render</b>\n"
        "  ├ /render_list — Список сервисов\n"
        "  ├ /render_status — Статус сервиса\n"
        "  ├ /render_restart — Перезапустить\n"
        "  ├ /render_env — Переменные окружения\n"
        "  └ /render_logs — Логи сервиса\n\n"
        
        "💾 <b>GitHub</b>\n"
        "  ├ /gh_list [путь] — Список файлов\n"
        "  ├ /gh_read [путь] — Прочитать файл\n"
        "  ├ /gh_write [путь] [текст] — Записать файл\n"
        "  ├ /gh_del [путь] — Удалить файл\n"
        "  ├ /gh_commits [N] — Коммиты\n"
        "  ├ /gh_branches — Ветки\n"
        "  └ /gh_repo — Инфо о репо\n\n"
        
        "🐦 <b>X Agent (Playwright)</b>\n"
        "  ├ /x_status — Проверить статус\n"
        "  ├ /x_install — Установить Chromium\n"
        "  ├ /x_login — Войти (ввод в чате)\n"
        "  ├ /x_login_env — Быстрый вход (env)\n"
        "  ├ /x_timeline [user] [N] — Лента X\n"
        "  ├ /x_search [запрос] [N] — Поиск X\n"
        "  └ /x_help — Помощь\n\n"
        
        "🚗 <b>X Agent (Selenium)</b>\n" +
        get_selenium_status_line() +
        "  ├ /se_status — Статус + аккаунт\n"
        "  ├ /se_install — Установить Selenium\n"
        "  ├ /se_google — Войти через Google\n"
        "  ├ /se_logout — Выйти\n"
        "  ├ /se_timeline [user] [N] — Лента\n"
        "  ├ /se_trends [N] — 🔥 Тренды\n"
        "  ├ /se_search [запрос] [N] — Поиск\n"
        "  ├ /se_screenshot [url] — Скриншот\n"
        "  └ /se_help — Помощь"
    )

@bot.message_handler(commands=["start", "help"])
def menu_command(message):
    try:
        log_action(message.text.lstrip("/"), f"user={message.from_user.id}", "info")
        bot.reply_to(message, build_menu_text(), parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")

@bot.message_handler(commands=["test"])
def test_command(message):
    bot.reply_to(message, "✅ Бот работает!")

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
