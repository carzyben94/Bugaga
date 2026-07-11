import os
import logging
import json
import subprocess
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import websockets

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

CHROME_PATH = "/usr/bin/google-chrome"

def start_chrome():
    """Запускает Chrome в фоновом режиме"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "google-chrome"],
            capture_output=True,
            text=True
        )
        
        if result.stdout:
            logger.info("✅ Chrome уже запущен")
            return True
        
        chrome_cmd = [
            CHROME_PATH,
            "--headless",
            "--remote-debugging-port=9222",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--user-data-dir=/tmp/chrome-profile"
        ]
        
        subprocess.Popen(
            chrome_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        time.sleep(3)
        logger.info("✅ Chrome запущен на порту 9222")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска Chrome: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("👋 Привет! Я бот с CDP на Railway.")

async def cdp_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает статус браузера"""
    try:
        async with websockets.connect("ws://localhost:9222/devtools/browser") as websocket:
            await websocket.send(json.dumps({
                "id": 1,
                "method": "Browser.getVersion"
            }))
            
            response = await websocket.recv()
            data = json.loads(response)
            
            if "result" in data:
                version = data["result"].get("product", "Unknown")
                user_agent = data["result"].get("userAgent", "Unknown")
                
                status_text = f"""✅ Браузер активен

📦 Версия: {version}
🌐 User-Agent: {user_agent}
🔌 Порт: 9222
📊 Статус: Подключен"""
                
                await update.message.reply_text(status_text)
            else:
                await update.message.reply_text("❌ Не удалось получить статус браузера")
                
    except Exception as e:
        await update.message.reply_text(f"""❌ Браузер не доступен

Ошибка: {str(e)}
💡 Проверьте, запущен ли Chrome на порту 9222""")
        logger.error(f"CDP error: {e}")

def main() -> None:
    # Запускаем Chrome перед ботом
    if not start_chrome():
        logger.warning("⚠️ Chrome не запустился")
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cdp", cdp_command))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()