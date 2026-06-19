import os
import sys
import time
import logging
import telebot
import selenium_x_agent as agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("Bot")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

bot = telebot.TeleBot(BOT_TOKEN)

try:
    bot.remove_webhook()
    print("✅ Webhook удалён")
except:
    pass


# ============ КОМАНДЫ ============

@bot.message_handler(commands=["start"])
def start_command(message):
    bot.send_message(
        message.chat.id,
        "🚀 Selenium X Agent\n\n"
        "📌 Команды:\n"
        "/status — статус системы\n"
        "/install — установить Chrome + Selenium\n"
        "/research — исследовать X.com\n"
        "/login — войти через Google\n"
        "/logs — отправить файл логов"
    )


@bot.message_handler(commands=["status"])
def status_command(message):
    st = agent.get_full_status()
    
    chrome_status = "✅" if st['chrome_browser']['found'] else "❌"
    driver_status = "✅" if st['chromedriver']['ready'] else "❌"
    selenium_status = "✅" if st['selenium_pip']['installed'] else "❌"
    ready_status = "🟢" if st['agent_ready'] else "🔴"
    cookies_status = "есть" if st['cookies_exist'] else "нет"
    
    chrome_path = st['chrome_browser']['path'] or 'не найден'
    driver_path = st['chromedriver']['path'] or 'не найден'
    selenium_installed = 'установлен' if st['selenium_pip']['installed'] else 'не установлен'
    ready = 'Да' if st['agent_ready'] else 'Нет'
    
    text = f"""✅ Chrome: {chrome_path}
✅ Driver: {driver_path}
✅ Selenium pip: {selenium_installed}
🟢 Готов: {ready}
🍪 Cookies: {cookies_status}
📁 {st['selenium_dir']}"""
    
    bot.reply_to(message, text)


@bot.message_handler(commands=["install"])
def install_command(message):
    if agent._installer.ready:
        try:
            import selenium
            bot.reply_to(message, "🟢 Уже установлено!")
            return
        except ImportError:
            pass
    
    msg = bot.reply_to(message, "⏳ Установка Chrome + Selenium...\n2-3 минуты")
    success = agent._installer.install()
    
    if success:
        bot.edit_message_text(
            f"✅ Установка завершена!\n\n"
            f"🌐 Chrome: {agent._installer.chrome_path}\n"
            f"🔧 Driver: {agent._installer.driver_path}",
            chat_id=msg.chat.id,
            message_id=msg.message_id
        )
    else:
        bot.edit_message_text(
            f"❌ Ошибка установки.\nЛоги: {agent.LOG_FILE}",
            chat_id=msg.chat.id,
            message_id=msg.message_id
        )


@bot.message_handler(commands=["research"])
def research_command(message):
    if not agent._installer.ready:
        bot.reply_to(message, "❌ Сначала /install")
        return
    
    msg = bot.reply_to(message, "🔍 Исследую X.com...\nВыгружаю все элементы...")
    
    try:
        result = agent.research_x_page("https://x.com/login", bot, message.chat.id)
        
        if "error" in result:
            bot.edit_message_text(f"❌ {result['error']}", chat_id=msg.chat.id, message_id=msg.message_id)
            return
        
        report = f"📊 *Исследование X.com (страница входа)*\n\n"
        report += f"🔗 URL: {result['url']}\n"
        report += f"🟦 Кнопок: {len(result['buttons'])}\n"
        report += f"🔗 Ссылок: {len(result['links'])}\n"
        report += f"📝 Полей ввода: {len(result['inputs'])}\n"
        report += f"📄 Текстовых элементов: {len(result['text_elements'])}\n\n"
        
        report += "🟦 *Найденные кнопки:*\n"
        for btn in result['buttons'][:15]:
            report += f"• {btn['text'][:60]}\n"
        
        # Проверяем наличие кнопки Google
        google_found = False
        for btn in result['buttons']:
            if 'google' in btn['text'].lower() or 'Google' in btn['text']:
                google_found = True
                report += f"\n✅ *Найдена кнопка Google!*"
                break
        
        if not google_found:
            report += f"\n⚠️ *Кнопка Google не найдена*"
            report += f"\n💡 Попробуй открыть /login вручную"
        
        bot.edit_message_text(report, chat_id=msg.chat.id, message_id=msg.message_id, parse_mode="Markdown")
        
        if "screenshot" in result and result["screenshot"]:
            try:
                with open(result["screenshot"], "rb") as f:
                    bot.send_photo(message.chat.id, f, caption="📸 Скриншот страницы входа")
            except:
                pass
        
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)[:200]}", chat_id=msg.chat.id, message_id=msg.message_id)


@bot.message_handler(commands=["login"])
def login_command(message):
    if not agent._installer.ready:
        bot.reply_to(message, "❌ Сначала /install")
        return
    
    chat_id = message.chat.id
    bot.reply_to(message, "🔐 *Вход через Google*\n\nВведи *email* от Google:", parse_mode="Markdown")
    agent.login_sessions[chat_id] = {"step": "google_email"}


@bot.message_handler(func=lambda m: m.chat.id in agent.login_sessions and agent.login_sessions[m.chat.id].get("step") == "google_email")
def login_google_email(message):
    chat_id = message.chat.id
    email = message.text.strip()
    
    if email.startswith("/"):
        del agent.login_sessions[chat_id]
        bot.reply_to(message, "❌ Отменено")
        return
    
    agent.login_sessions[chat_id]["email"] = email
    agent.login_sessions[chat_id]["step"] = "google_password"
    bot.reply_to(message, f"✅ Email: <code>{email}</code>\n\nВведи *пароль*:", parse_mode="HTML")


@bot.message_handler(func=lambda m: m.chat.id in agent.login_sessions and agent.login_sessions[m.chat.id].get("step") == "google_password")
def login_google_password(message):
    chat_id = message.chat.id
    password = message.text.strip()
    
    if password.startswith("/"):
        del agent.login_sessions[chat_id]
        bot.reply_to(message, "❌ Отменено")
        return
    
    email = agent.login_sessions[chat_id]["email"]
    del agent.login_sessions[chat_id]
    
    msg = bot.reply_to(message, "⏳ Вхожу через Google...\n30-60 секунд")
    
    success, error = agent.run_sync_task(
        agent.google_login,
        email,
        password,
        bot,
        chat_id
    )
    
    try:
        bot.delete_message(chat_id, msg.message_id)
    except:
        pass
    
    if error:
        bot.reply_to(message, f"❌ {error}")
    elif success:
        auth = agent.get_auth_info()
        bot.reply_to(
            message,
            f"✅ *Вход успешен!*\n"
            f"👤 @{auth['username'] if auth else '?'}\n"
            f"📧 {email}\n\n"
            f"📊 Проверь /status",
            parse_mode="Markdown"
        )
    else:
        bot.reply_to(message, "❌ Вход не удался")


@bot.message_handler(commands=["logs"])
def logs_command(message):
    log_file = agent.LOG_FILE
    
    if not log_file.exists():
        bot.reply_to(message, "❌ Файл логов не найден")
        return
    
    try:
        with open(log_file, "rb") as f:
            bot.send_document(
                message.chat.id,
                f,
                caption=f"📋 Логи агента\n📁 {log_file}\n📅 {time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:200]}")


@bot.message_handler(func=lambda m: True)
def fallback(message):
    bot.reply_to(
        message,
        "🤖 Команды:\n"
        "/start — меню\n"
        "/status — статус\n"
        "/install — установка\n"
        "/research — исследовать X.com\n"
        "/login — войти через Google\n"
        "/logs — отправить файл логов"
    )


if __name__ == "__main__":
    print("🚀 Запуск бота...")
    print(f"📁 Директория: {agent.BASE_DIR}")
    
    try:
        bot.remove_webhook()
        print("✅ Webhook удалён")
    except:
        pass
    
    bot.infinity_polling()