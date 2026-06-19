import os
import sys
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
    raise ValueError("TELEGRAM_BOT_TOKEN не задан! Добавь переменную на Render")

bot = telebot.TeleBot(BOT_TOKEN)

# ============ УДАЛЯЕМ WEBHOOK ПРИ СТАРТЕ ============
try:
    bot.remove_webhook()
    print("✅ Webhook удалён, использую polling")
except Exception as e:
    print(f"⚠️ Ошибка удаления webhook: {e}")

# ============ КОМАНДЫ ============

@bot.message_handler(commands=["start"])
def start_command(message):
    bot.send_message(
        message.chat.id,
        "🚀 Selenium X Agent\n\n"
        "📌 Команды:\n"
        "/status — статус системы\n"
        "/install — установить Chrome + Selenium"
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

@bot.message_handler(func=lambda m: True)
def fallback(message):
    bot.reply_to(message, "🤖 /start — меню\n/status — статус\n/install — установка")

if __name__ == "__main__":
    print("🚀 Запуск бота...")
    print(f"📁 Директория: {agent.BASE_DIR}")
    
    # Ещё раз удаляем webhook перед запуском
    try:
        bot.remove_webhook()
        print("✅ Webhook удалён")
    except:
        pass
    
    # Запускаем polling
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)