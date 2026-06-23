import os
import asyncio
import telebot
from browser import Browser

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

bot = telebot.TeleBot(TOKEN)

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
browser = None
loop = None


def run_async(coro):
    """Запуск асинхронной функции"""
    global loop
    if loop is None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, 
        "👋 Привет!\n"
        "Команды:\n"
        "/browser — Запустить браузер\n"
        "/close — Закрыть браузер\n"
        "/screen — Скриншот\n"
        "/google — Открыть Google"
    )


@bot.message_handler(commands=['browser'])
def start_browser(message):
    global browser
    
    if browser:
        bot.reply_to(message, "✅ Браузер уже запущен")
        return
    
    try:
        browser = Browser(headless=True)
        run_async(browser.start())
        bot.reply_to(message, "✅ Браузер запущен!")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")


@bot.message_handler(commands=['close'])
def close_browser(message):
    global browser
    
    if not browser:
        bot.reply_to(message, "❌ Браузер не запущен")
        return
    
    try:
        run_async(browser.close())
        browser = None
        bot.reply_to(message, "✅ Браузер закрыт")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")


@bot.message_handler(commands=['screen'])
def screenshot(message):
    global browser
    
    if not browser:
        bot.reply_to(message, "❌ Сначала /browser")
        return
    
    try:
        filename = f"screen_{message.from_user.id}.png"
        run_async(browser.screenshot(filename))
        
        with open(filename, "rb") as f:
            bot.send_photo(message.chat.id, f, caption="📸 Скриншот")
        
        os.remove(filename)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")


@bot.message_handler(commands=['google'])
def open_google(message):
    global browser
    
    if not browser:
        bot.reply_to(message, "❌ Сначала /browser")
        return
    
    try:
        run_async(browser.goto("https://google.com"))
        bot.reply_to(message, "✅ Google открыт! /screen чтобы посмотреть")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)[:100]}")


@bot.message_handler(func=lambda m: True)
def echo(message):
    bot.reply_to(message, "Используй /start")


if __name__ == '__main__':
    print("🤖 Бот запущен!")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot.polling(non_stop=True, interval=1)