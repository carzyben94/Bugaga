import os
import logging
import subprocess
import asyncio
import httpx
import websockets
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ==================== НАСТРОЙКА ЛОГГИРОВАНИЯ ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ==================== ЗАПУСК CHROME ====================
CHROME_PATH = "/usr/bin/chromium"

def start_chrome():
    """Запускает Chromium в headless-режиме с удалённой отладкой"""
    try:
        subprocess.Popen([
            CHROME_PATH,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--remote-debugging-port=9222"
        ])
        logger.info("✅ Chrome/Chromium успешно запущен (debug port: 9222)")
        return True
    except FileNotFoundError:
        logger.error("❌ Chrome не найден по пути: %s", CHROME_PATH)
        return False
    except Exception as e:
        logger.error("❌ Ошибка запуска Chrome: %s", e)
        return False

# ==================== ПОЛУЧЕНИЕ WEBSOCKET URL ====================
async def get_websocket_url():
    """Получает WebSocket URL для подключения к Chrome через httpx"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:9222/json/list", timeout=5.0)
            pages = resp.json()
            if pages:
                ws_url = pages[0]["webSocketDebuggerUrl"]
                logger.info(f"✅ WebSocket URL получен: {ws_url}")
                return ws_url
            else:
                logger.error("❌ Нет открытых страниц в Chrome")
                return None
    except Exception as e:
        logger.error(f"❌ Ошибка получения WebSocket URL: {e}")
        return None

# ==================== ПРИМЕР РАБОТЫ С WEBSOCKET ====================
async def test_websocket():
    """Тестовое подключение к Chrome через WebSocket"""
    ws_url = await get_websocket_url()
    if not ws_url:
        return
    
    try:
        async with websockets.connect(ws_url) as websocket:
            logger.info("✅ Подключение к Chrome через WebSocket установлено")
            # Отправляем команду для получения версии браузера
            await websocket.send('{"id": 1, "method": "Browser.getVersion"}')
            response = await websocket.recv()
            logger.info(f"Ответ от Chrome: {response[:200]}...")
    except Exception as e:
        logger.error(f"❌ Ошибка WebSocket: {e}")

# ==================== ТОКЕН БОТА ====================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не установлен в переменных окружения!")

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ на команду /start"""
    ws_url = await get_websocket_url()
    if ws_url:
        await update.message.reply_text(
            f"👋 Привет! Бот запущен и работает.\n\n"
            f"✅ Chrome готов к работе\n"
            f"🔗 WebSocket: {ws_url[:50]}..."
        )
    else:
        await update.message.reply_text(
            "👋 Привет! Бот запущен и работает.\n\n"
            "❌ Chrome не доступен"
        )

# ==================== ЗАПУСК БОТА ====================
def main():
    """Главная функция запуска бота"""
    logger.info("🚀 Запуск бота...")
    
    # Запускаем Chrome
    start_chrome()
    
    # Тестовое подключение к WebSocket
    asyncio.run(test_websocket())
    
    # Создаём и настраиваем приложение
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    
    # Запускаем поллинг
    logger.info("✅ Бот успешно запущен! Ожидание команд...")
    app.run_polling()

# ==================== ТОЧКА ВХОДА ====================
if __name__ == "__main__":
    main()