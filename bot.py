# bot.py
import os
import subprocess
import sys
import time
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

CLOAK_DIR = "/app/cloak"
CLOAK_BINARY = f"{CLOAK_DIR}/cloak"

def install_cloak():
    """Автоматическая установка CloakBrowser"""
    logger.info("Начинаю установку CloakBrowser...")
    
    # Создаем директорию
    os.makedirs(CLOAK_DIR, exist_ok=True)
    
    # Скачиваем последнюю версию (Linux x86_64)
    subprocess.run([
        "wget", "-O", f"{CLOAK_DIR}/cloak.tar.gz",
        "https://github.com/coder3101/cloak/releases/latest/download/cloak-linux-amd64.tar.gz"
    ], check=True)
    
    # Распаковываем
    subprocess.run([
        "tar", "-xzf", f"{CLOAK_DIR}/cloak.tar.gz", 
        "-C", CLOAK_DIR
    ], check=True)
    
    # Делаем исполняемым
    os.chmod(CLOAK_BINARY, 0o755)
    
    logger.info("CloakBrowser успешно установлен!")

# Проверяем и устанавливаем Cloak при запуске
if not os.path.exists(CLOAK_BINARY):
    install_cloak()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "🤖 CloakBrowser готов к работе!\n"
        "Используйте /browse <URL> для открытия страницы\n"
        "Пример: /browse https://example.com"
    )

async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открывает URL через CloakBrowser"""
    if not context.args:
        await update.message.reply_text("❌ Укажите URL: /browse https://example.com")
        return
    
    url = context.args[0]
    
    # Запускаем CloakBrowser
    try:
        process = subprocess.Popen(
            [CLOAK_BINARY, "open", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Ждем немного для вывода
        time.sleep(2)
        stdout, stderr = process.communicate(timeout=5)
        
        if stderr:
            await update.message.reply_text(f"⚠️ Ошибка: {stderr[:200]}")
        else:
            await update.message.reply_text(f"✅ Открыто: {url}")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

def main():
    """Запуск бота"""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("browse", browse))
    
    logger.info("Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()