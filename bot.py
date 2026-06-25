import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# ВЫВОДИМ ВСЕ ПЕРЕМЕННЫЕ ДЛЯ ОТЛАДКИ
logging.info("=" * 50)
logging.info("🔍 ВСЕ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ:")
for key, value in os.environ.items():
    if "TOKEN" in key or "KEY" in key or "SECRET" in key:
        logging.info(f"  {key}: {'✅' if value else '❌ ПУСТО'}")
    else:
        logging.info(f"  {key}: {value[:20] if value else '❌ ПУСТО'}")
logging.info("=" * 50)

# Пробуем получить токен разными способами
TOKEN = os.getenv("TELEGRAM_TOKEN_BOT") or os.getenv("BOT_TOKEN") or os.getenv("TOKEN")

logging.info(f"📌 Итоговый токен: {'✅ НАЙДЕН' if TOKEN else '❌ НЕ НАЙДЕН'}")

if not TOKEN:
    logging.error("❌ TELEGRAM_TOKEN_BOT не найден!")
    logging.error("💡 Проверьте название переменной в Railway")
    logging.error("💡 Должно быть ТОЧНО: TELEGRAM_TOKEN_BOT")
    # Не останавливаем бота, а даём вторую попытку
    TOKEN = "TEST_TOKEN_FOR_DEBUG"  # Временный токен для отладки

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот работает!\n"
        "Команда:\n"
        "/start - приветствие\n"
        "/check - проверить переменные"
    )

# Команда /check - показать переменные
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token_status = "✅ Есть" if os.getenv("TELEGRAM_TOKEN_BOT") else "❌ Нет"
    
    message = (
        "🔍 <b>Проверка переменных:</b>\n\n"
        f"TELEGRAM_TOKEN_BOT: {token_status}\n"
        f"RAILWAY_STATIC_URL: {os.getenv('RAILWAY_STATIC_URL', '❌ Нет')}\n"
        f"PORT: {os.getenv('PORT', '❌ Нет')}\n"
    )
    
    await update.message.reply_text(message, parse_mode="HTML")

def main():
    # Создаём приложение
    app = Application.builder().token(TOKEN).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check))
    
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