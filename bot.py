# bot.py - Полная версия для Playwright X Agent
import os
import sys
import time
import logging
import json
from flask import Flask, request
import telebot
from datetime import datetime

print("[DEBUG] Запуск бота...", flush=True)

# === ИМПОРТ PLAYWRIGHT ===
PLAYWRIGHT_AVAILABLE = False
register_commands = None
get_full_status = None
get_auth_info = None
AGENT_READY = None
BASE_DIR = None
create_browser = None
Browser = None
google_login = None
clear_auth = None

print("[DEBUG] Импорт playwright_x_agent...", flush=True)
try:
    from playwright_x_agent import (
        register_commands as _rc,
        get_full_status as _gfs,
        get_auth as _ga,
        is_ready as _ar,
        BASE_DIR as _bd,
        create_browser as _cb,
        Browser as _br,
        google_login as _gl,
        clear_auth as _ca
    )
    register_commands = _rc
    get_full_status = _gfs
    get_auth_info = _ga
    AGENT_READY = _ar
    BASE_DIR = _bd
    create_browser = _cb
    Browser = _br
    google_login = _gl
    clear_auth = _ca
    PLAYWRIGHT_AVAILABLE = True
    print("[DEBUG] ✅ Playwright импортирован успешно", flush=True)
except Exception as e:
    print(f"[DEBUG] ❌ Ошибка импорта: {e}", flush=True)
    import traceback
    traceback.print_exc()

# === НАСТРОЙКА ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Bot")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not set")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
login_sessions = {}
browser_sessions = {}

# === МЕНЮ ===
def build_menu():
    """Главное меню"""
    if not PLAYWRIGHT_AVAILABLE:
        return (
            "🚫 <b>Playwright не загружен</b>\n\n"
            "❌ Проверь логи: /se_logs"
        )
    
    try:
        status = get_full_status()
        ready = status.get("ready", False)
        auth = status.get("auth")
        version = status.get("version", "?")
        
        # Статус
        if ready and auth:
            status_icon = "🟢"
            status_text = "✅ Активен"
        elif ready and not auth:
            status_icon = "🟡"
            status_text = "⏳ Ожидает входа"
        else:
            status_icon = "🔴"
            status_text = "❌ Не готов"
        
        # Пользователь
        user_info = f"👤 <b>{auth['username']}</b>" if auth else "👤 <i>не авторизован</i>"
        
        return f"""
🚗 <b>PLAYWRIGHT X AGENT</b>
{'━' * 30}

{status_icon} <b>Статус:</b> {status_text}

{user_info}

📦 <b>Компоненты:</b>
✅ Playwright: {version}
{'✅' if ready else '❌'} Браузер: {'готов' if ready else 'не установлен'}

📁 {status.get('base_dir', BASE_DIR)}
🕐 {datetime.now().strftime('%H:%M:%S')}

📋 /help — список команд
"""
    except Exception as e:
        return f"⚠️ Ошибка: {e}"

# === ОСНОВНЫЕ КОМАНДЫ ===
@bot.message_handler(commands=["start", "menu"])
def menu_command(message):
    bot.reply_to(message, build_menu(), parse_mode="HTML")

@bot.message_handler(commands=["help"])
def help_command(message):
    text = """
📋 <b>ПОЛНЫЙ СПИСОК КОМАНД</b>
{'━' * 30}

<b>ОСНОВНЫЕ:</b>
/start      - Главное меню
/help       - Помощь
/menu       - Показать меню

<b>УПРАВЛЕНИЕ:</b>
/se_status  - Статус агента
/se_install - Установка Playwright
/se_clear   - Очистить логи
/se_logs    - Показать логи

<b>АВТОРИЗАЦИЯ:</b>
/se_google  - Вход через Google
/se_logout  - Выйти

<b>БРАУЗЕР:</b>
/se_browser - Запустить браузер
/se_screenshot - Скриншот
/se_close   - Закрыть браузер

<b>ДИАГНОСТИКА:</b>
/se_ping    - Пинг бота
/se_test    - Тест
"""
    bot.reply_to(message, text, parse_mode="HTML")

# === УПРАВЛЕНИЕ ===
@bot.message_handler(commands=["se_status"])
def status_command(message):
    if not PLAYWRIGHT_AVAILABLE:
        bot.reply_to(message, "❌ Playwright не загружен", parse_mode="HTML")
        return
    
    try:
        status = get_full_status()
        auth = status.get("auth")
        ready = status.get("ready", False)
        version = status.get("version", "?")
        
        text = f"""
🚗 <b>Playwright X Agent</b>
{'─' * 30}

✅ Playwright: {version}
{'🟢' if ready else '🔴'} Готов: {'Да' if ready else 'Нет'}

👤 Авторизация: {'✅' if auth else '❌'}
🍪 Cookies: {'есть' if status.get('cookies') else 'нет'}
🌐 Сессий: {status.get('sessions', 0)}

📁 {status.get('base_dir', BASE_DIR)}
"""
        bot.reply_to(message, text, parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}", parse_mode="HTML")

@bot.message_handler(commands=["se_install"])
def install_command(message):
    if not PLAYWRIGHT_AVAILABLE:
        bot.reply_to(message, "❌ Playwright не загружен", parse_mode="HTML")
        return
    
    if AGENT_READY():
        bot.reply_to(message, "✅ Уже установлено! Используй /se_status", parse_mode="HTML")
        return
    
    msg = bot.reply_to(message, "⏳ Установка Playwright + Chromium...\nЭто займет 2-3 минуты", parse_mode="HTML")
    
    try:
        from playwright_x_agent import install_playwright
        success = install_playwright()
        
        if success:
            bot.edit_message_text(
                f"✅ <b>Установка завершена!</b>\n\n"
                f"📦 Playwright установлен\n"
                f"🌐 Chromium установлен\n\n"
                f"Теперь используй /se_google для входа",
                chat_id=msg.chat.id,
                message_id=msg.message_id,
                parse_mode="HTML"
            )
        else:
            bot.edit_message_text(
                "❌ <b>Ошибка установки</b>\n"
                f"Проверь логи: /se_logs",
                chat_id=msg.chat.id,
                message_id=msg.message_id,
                parse_mode="HTML"
            )
    except Exception as e:
        bot.edit_message_text(
            f"❌ Ошибка: {e}",
            chat_id=msg.chat.id,
            message_id=msg.message_id
        )

@bot.message_handler(commands=["se_logs"])
def logs_command(message):
    try:
        log_file = BASE_DIR / "agent.log" if BASE_DIR else None
        if log_file and log_file.exists():
            with open(log_file, "rb") as f:
                bot.send_document(
                    message.chat.id,
                    f,
                    caption="📄 Логи агента",
                    visible_file_name="agent.log"
                )
        else:
            bot.reply_to(message, "❌ Лог-файл не найден", parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}", parse_mode="HTML")

@bot.message_handler(commands=["se_clear"])
def clear_command(message):
    try:
        log_file = BASE_DIR / "agent.log" if BASE_DIR else None
        if log_file and log_file.exists():
            log_file.write_text("")
            bot.reply_to(message, "🧹 Логи очищены", parse_mode="HTML")
        else:
            bot.reply_to(message, "❌ Лог-файл не найден", parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}", parse_mode="HTML")

# === АВТОРИЗАЦИЯ ===
@bot.message_handler(commands=["se_google"])
def google_command(message):
    if not PLAYWRIGHT_AVAILABLE:
        bot.reply_to(message, "❌ Playwright не загружен", parse_mode="HTML")
        return
    
    if not AGENT_READY():
        bot.reply_to(message, "❌ Сначала /se_install", parse_mode="HTML")
        return
    
    chat_id = message.chat.id
    login_sessions[chat_id] = {"step": "email"}
    bot.reply_to(message, "🔐 Введи <b>email</b> от Google:", parse_mode="HTML")

@bot.message_handler(commands=["se_logout"])
def logout_command(message):
    if not PLAYWRIGHT_AVAILABLE:
        bot.reply_to(message, "❌ Playwright не загружен", parse_mode="HTML")
        return
    
    try:
        if clear_auth:
            clear_auth()
        bot.reply_to(message, "🚪 Сессия очищена", parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}", parse_mode="HTML")

# === БРАУЗЕР ===
@bot.message_handler(commands=["se_browser"])
def browser_command(message):
    if not PLAYWRIGHT_AVAILABLE:
        bot.reply_to(message, "❌ Playwright не загружен", parse_mode="HTML")
        return
    
    if not AGENT_READY():
        bot.reply_to(message, "❌ Сначала /se_install", parse_mode="HTML")
        return
    
    chat_id = message.chat.id
    
    if chat_id in browser_sessions:
        try:
            browser_sessions[chat_id].stop()
        except:
            pass
        del browser_sessions[chat_id]
    
    msg = bot.reply_to(message, "⏳ Запускаю браузер (Playwright)...", parse_mode="HTML")
    
    try:
        browser = create_browser(headless=True, mobile=False, chat_id=chat_id)
        browser.goto("https://x.com")
        browser_sessions[chat_id] = browser
        
        screenshot_path = browser.screenshot("browser_start")
        
        response = "✅ Браузер запущен!\n"
        response += f"📄 Title: {browser.title()}\n"
        
        if screenshot_path:
            with open(screenshot_path, "rb") as f:
                bot.send_photo(chat_id, f, caption=response)
            bot.delete_message(chat_id, msg.message_id)
        else:
            bot.edit_message_text(response, chat_id=chat_id, message_id=msg.message_id, parse_mode="HTML")
            
    except Exception as e:
        bot.edit_message_text(
            f"❌ Ошибка: {e}",
            chat_id=chat_id,
            message_id=msg.message_id
        )

@bot.message_handler(commands=["se_screenshot"])
def screenshot_command(message):
    chat_id = message.chat.id
    
    if chat_id not in browser_sessions:
        bot.reply_to(message, "❌ Браузер не запущен. Используй /se_browser", parse_mode="HTML")
        return
    
    try:
        browser = browser_sessions[chat_id]
        screenshot_path = browser.screenshot("manual")
        
        if screenshot_path:
            with open(screenshot_path, "rb") as f:
                bot.send_photo(
                    chat_id, f,
                    caption=f"📸 Скриншот\n🌐 {browser.title()}"
                )
        else:
            bot.reply_to(message, "❌ Не удалось сделать скриншот", parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}", parse_mode="HTML")

@bot.message_handler(commands=["se_close"])
def close_command(message):
    chat_id = message.chat.id
    
    if chat_id in browser_sessions:
        try:
            browser_sessions[chat_id].stop()
            del browser_sessions[chat_id]
            bot.reply_to(message, "✅ Браузер закрыт", parse_mode="HTML")
        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка: {e}", parse_mode="HTML")
    else:
        bot.reply_to(message, "ℹ️ Браузер не запущен", parse_mode="HTML")

# === ДИАГНОСТИКА ===
@bot.message_handler(commands=["se_ping"])
def ping_command(message):
    bot.reply_to(
        message,
        f"🏓 Pong! {datetime.now().strftime('%H:%M:%S')}",
        parse_mode="HTML"
    )

@bot.message_handler(commands=["se_test"])
def test_command(message):
    bot.reply_to(
        message,
        f"✅ Бот работает!\n🕐 {datetime.now().strftime('%H:%M:%S')}\n"
        f"📦 Playwright: {'✅' if PLAYWRIGHT_AVAILABLE else '❌'}",
        parse_mode="HTML"
    )

# === ОБРАБОТЧИКИ ВХОДА ===
@bot.message_handler(func=lambda m: m.chat.id in login_sessions and login_sessions[m.chat.id].get("step") == "email")
def handle_email(message):
    chat_id = message.chat.id
    email = message.text.strip()
    
    if email.startswith("/"):
        del login_sessions[chat_id]
        bot.reply_to(message, "❌ Отменено", parse_mode="HTML")
        return
    
    login_sessions[chat_id]["email"] = email
    login_sessions[chat_id]["step"] = "password"
    bot.reply_to(message, f"✅ Email: <code>{email}</code>\n\nТеперь введи <b>пароль</b>:", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.chat.id in login_sessions and login_sessions[m.chat.id].get("step") == "password")
def handle_password(message):
    chat_id = message.chat.id
    password = message.text
    
    if password.startswith("/"):
        del login_sessions[chat_id]
        bot.reply_to(message, "❌ Отменено", parse_mode="HTML")
        return
    
    email = login_sessions[chat_id]["email"]
    del login_sessions[chat_id]
    
    bot.reply_to(message, "⏳ Вхожу через Google...\n<i>30-60 сек</i>", parse_mode="HTML")
    
    try:
        if google_login:
            success, error = google_login(email, password, bot, chat_id)
            
            if error:
                bot.reply_to(message, f"❌ {error}", parse_mode="HTML")
            elif success:
                auth = get_auth_info()
                bot.reply_to(
                    message,
                    f"✅ Вход успешен!\n👤 @{auth['username'] if auth else '?'}",
                    parse_mode="HTML"
                )
            else:
                bot.reply_to(message, "❌ Вход не удался", parse_mode="HTML")
        else:
            bot.reply_to(message, "❌ Функция google_login не доступна", parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}", parse_mode="HTML")

# === WEBHOOK ===
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

# === ЗАПУСК ===
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