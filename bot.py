import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота
TOKEN = os.getenv("TELEGRAM_TOKEN_BOT")

if not TOKEN:
    logging.error("❌ TELEGRAM_TOKEN_BOT не найден!")
    raise ValueError("Добавьте TELEGRAM_TOKEN_BOT в переменные Railway")

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот работает!\n"
        "Команда:\n"
        "/start - приветствие"
    )

def main():
    # Создаём приложение
    app = Application.builder().token(TOKEN).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    
    # Запуск на Railway
    port = int(os.getenv("PORT", 8080))
    webhook_url = f"https://{os.getenv('RAILWAY_STATIC_URL')}/webhook"
    
    logging.info(f"🚀 Запуск бота на порту {port}")
    logging.info(f"🔗 Webhook: {webhook_url}")
    
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=webhook_url
    )

if __name__ == "__main__":
    main()