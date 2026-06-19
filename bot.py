import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request
import os
import logging
import subprocess
import sys
from browser_manager import PlaywrightBrowser, get_browser_info
from pathlib import Path

# ========== КОНФИГУРАЦИЯ ==========
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-domain.com/webhook")
PORT = int(os.getenv("PORT", 5000))

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Глобальный экземпляр браузера
browser_instance = None

def get_browser():
    """Получает или создает экземпляр браузера"""
    global browser_instance
    if browser_instance is None:
        logger.info("Инициализация браузера...")
        browser_instance = PlaywrightBrowser(headless=True, browser_type="chromium")
        browser_instance.start()
    return browser_instance

# ========== КЛАВИАТУРА ==========
def get_main_keyboard():
    """Создает главную клавиатуру с кнопками"""
    keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    
    btn_screenshot = KeyboardButton("📸 Сделать скриншот")
    btn_install = KeyboardButton("⬇️ Установить браузер")
    btn_info = KeyboardButton("ℹ️ Информация о браузере")
    btn_help = KeyboardButton("❓ Помощь")
    
    keyboard.add(btn_screenshot, btn_install)
    keyboard.add(btn_info, btn_help)
    
    return keyboard

def get_cancel_keyboard():
    """Клавиатура для отмены"""
    keyboard = ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    keyboard.add(KeyboardButton("❌ Отмена"))
    return keyboard

# ========== ОБРАБОТЧИКИ КОМАНД ==========
@bot.message_handler(commands=["start"])
def start_message(message):
    """Приветственное сообщение с меню"""
    bot.send_message(
        message.chat.id,
        f"👋 Привет, {message.from_user.first_name}!\n"
        f"Я бот с поддержкой Playwright браузера\n\n"
        f"📌 Используй кнопки ниже или команды:\n"
        f"/screenshot <url> - скриншот сайта\n"
        f"/install_browser - установить браузер\n"
        f"/browser_info - информация о браузере",
        reply_markup=get_main_keyboard()
    )

@bot.message_handler(commands=["screenshot"])
def screenshot_command(message):
    """Делает скриншот указанного URL"""
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "❌ Укажите URL: /screenshot https://example.com")
            return
        
        url = parts[1].strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        # Проверяем установлен ли браузер
        info = get_browser_info()
        if not info["installed"]:
            bot.reply_to(
                message,
                "❌ Браузер не установлен!\n"
                "Нажми кнопку '⬇️ Установить браузер' или /install_browser"
            )
            return
        
        bot.reply_to(message, f"🔄 Делаю скриншот {url}...")
        
        browser = get_browser()
        screenshot_bytes = browser.screenshot(url, full_page=True)
        
        bot.send_photo(
            message.chat.id,
            screenshot_bytes,
            caption=f"📸 Скриншот: {url}"
        )
        
    except Exception as e:
        logger.error(f"Screenshot error: {e}")
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")

@bot.message_handler(commands=["install_browser"])
def install_browser_command(message):
    """Установка браузера"""
    bot.reply_to(
        message,
        "⬇️ Начинаю установку браузера...\n"
        "Это может занять несколько минут ⏳"
    )
    
    try:
        # Устанавливаем playwright
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "playwright"],
            check=True,
            capture_output=True
        )
        
        # Устанавливаем браузер
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            capture_output=True
        )
        
        # Пересоздаем экземпляр браузера
        global browser_instance
        if browser_instance:
            browser_instance.close()
            browser_instance = None
        
        bot.reply_to(
            message,
            "✅ Браузер успешно установлен!\n"
            "Теперь можно делать скриншоты 📸",
            reply_markup=get_main_keyboard()
        )
        
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        logger.error(f"Install error: {error_msg}")
        bot.reply_to(
            message,
            f"❌ Ошибка установки:\n{error_msg[:200]}"
        )

@bot.message_handler(commands=["browser_info"])
def browser_info_command(message):
    """Показывает информацию о браузере"""
    info = get_browser_info()
    
    if info["installed"]:
        browsers_text = "\n".join([f"• {b}" for b in info["browsers"]])
        response = (
            f"✅ Браузеры установлены:\n{browsers_text}\n\n"
            f"💡 Всего установлено: {len(info['browsers'])}"
        )
    else:
        response = (
            "❌ Браузеры не установлены\n\n"
            "Нажми кнопку '⬇️ Установить браузер'"
        )
    
    bot.reply_to(message, response, reply_markup=get_main_keyboard())

@bot.message_handler(commands=["help"])
def help_command(message):
    """Помощь"""
    bot.send_message(
        message.chat.id,
        "📖 Помощь:\n\n"
        "🔹 /screenshot <url> - сделать скриншот сайта\n"
        "🔹 /install_browser - установить браузер\n"
        "🔹 /browser_info - информация о браузере\n"
        "🔹 /start - показать меню\n\n"
        "Или используй кнопки ниже 👇",
        reply_markup=get_main_keyboard()
    )

# ========== ОБРАБОТЧИК КНОПОК ==========
@bot.message_handler(func=lambda message: message.text == "📸 Сделать скриншот")
def button_screenshot(message):
    """Обработка кнопки скриншота"""
    bot.reply_to(
        message,
        "🌐 Введите URL сайта для скриншота:\n"
        "Например: https://example.com",
        reply_markup=get_cancel_keyboard()
    )
    # Устанавливаем состояние ожидания URL
    bot.register_next_step_handler(message, process_screenshot_url)

@bot.message_handler(func=lambda message: message.text == "⬇️ Установить браузер")
def button_install_browser(message):
    """Обработка кнопки установки браузера"""
    install_browser_command(message)

@bot.message_handler(func=lambda message: message.text == "ℹ️ Информация о браузере")
def button_browser_info(message):
    """Обработка кнопки информации о браузере"""
    browser_info_command(message)

@bot.message_handler(func=lambda message: message.text == "❓ Помощь")
def button_help(message):
    """Обработка кнопки помощи"""
    help_command(message)

@bot.message_handler(func=lambda message: message.text == "❌ Отмена")
def button_cancel(message):
    """Обработка кнопки отмены"""
    bot.reply_to(
        message,
        "✅ Действие отменено",
        reply_markup=get_main_keyboard()
    )

def process_screenshot_url(message):
    """Обработка введенного URL для скриншота"""
    if message.text == "❌ Отмена":
        bot.reply_to(message, "✅ Отменено", reply_markup=get_main_keyboard())
        return
    
    url = message.text.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    # Проверяем установлен ли браузер
    info = get_browser_info()
    if not info["installed"]:
        bot.reply_to(
            message,
            "❌ Браузер не установлен!\n"
            "Нажми кнопку '⬇️ Установить браузер'",
            reply_markup=get_main_keyboard()
        )
        return
    
    try:
        bot.reply_to(message, f"🔄 Делаю скриншот {url}...")
        
        browser = get_browser()
        screenshot_bytes = browser.screenshot(url, full_page=True)
        
        bot.send_photo(
            message.chat.id,
            screenshot_bytes,
            caption=f"📸 Скриншот: {url}",
            reply_markup=get_main_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Screenshot error: {e}")
        bot.reply_to(
            message,
            f"❌ Ошибка: {str(e)[:200]}",
            reply_markup=get_main_keyboard()
        )

# ========== WEBHOOK ==========
@app.route("/webhook", methods=["POST"])
def webhook():
    """Эндпоинт для вебхуков Telegram"""
    try:
        json_str = request.get_data().decode("UTF-8")
        update = telebot.types.Update.de_json(json_str)
        
        if update:
            bot.process_new_updates([update])
            logger.info("Update processed successfully")
            return "OK", 200
        return "No update", 400
            
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "Error", 500

@app.route("/", methods=["GET"])
def health_check():
    """Проверка работоспособности"""
    return "Bot is running", 200

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    # При старте проверяем браузер
    try:
        info = get_browser_info()
        if info["installed"]:
            logger.info(f"Браузер найден: {info['browsers']}")
        else:
            logger.warning("Браузер не установлен. Нажмите кнопку установки")
    except Exception as e:
        logger.error(f"Ошибка проверки браузера: {e}")
    
    if os.getenv("ENV") == "production":
        logger.info(f"Starting webhook mode on port {PORT}")
        
        try:
            bot.remove_webhook()
            bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
            logger.info(f"Webhook set to {WEBHOOK_URL}/webhook")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
        
        app.run(host="0.0.0.0", port=PORT)
    else:
        logger.info("Starting polling mode (development)")
        bot.remove_webhook()
        bot.infinity_polling(timeout=30, long_polling_timeout=30)