# bot.py — Только Selenium X Agent
import os
import sys
import time
import logging
import json
from flask import Flask, request
import telebot

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not set")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

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

# === МЕНЮ ===
def build_menu_text():
    if not SELENIUM_AVAILABLE:
        return "❌ <b>Selenium модуль не загружен</b>\n\nПроверь логи."
    
    try:
        status = get_full_status()
        ready = status.get("agent_ready", False)
        auth = status.get("auth_info")
        
        auth_line = f"👤 <code>@{auth['username']}</code>\n" if auth else "👤 <i>не подключён</i>\n"
        icon = "🟢" if ready else "🔴"
        
        return (
            "🚗 <b>Selenium X Agent</b>\n\n"
            f"{auth_line}"
            f"{icon} Готов: {'Да' if ready else 'Нет'}\n\n"
            "/se_status — Статус\n"
            "/se_install — Установить Chrome\n"
            "/se_google — Войти через Google\n"
        )
    except Exception as e:
        return f"⚠️ Ошибка статуса: {e}"

@bot.message_handler(commands=["start", "help"])
def menu_command(message):
    bot.reply_to(message, build_menu_text(), parse_mode="HTML")

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
    
    try:
        bot.remove_webhook()
        time.sleep(2)
    except:
        pass
    
    try:
        bot.set_webhook(url=f"{url}/{TELEGRAM_TOKEN}")
        print("✅ Webhook установлен!")
    except Exception as e:
        print(f"set webhook error: {e}")
    
    app.run(host="0.0.0.0", port=port)
