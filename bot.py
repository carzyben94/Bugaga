import os
import logging
import json
import subprocess
import time
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters, MessageHandler
import websockets
import base64

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

CHROME_PATH = "/usr/bin/google-chrome"
chrome_ws_url = None

# ---------- Запуск Chrome ----------

def start_chrome():
    try:
        result = subprocess.run(["pgrep", "-f", "google-chrome"], capture_output=True, text=True)
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
        
        subprocess.Popen(chrome_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        time.sleep(5)
        logger.info("✅ Chrome запущен")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False

def get_websocket_url():
    global chrome_ws_url
    try:
        response = requests.get("http://localhost:9222/json/version")
        chrome_ws_url = response.json().get("webSocketDebuggerUrl")
        logger.info(f"✅ WebSocket: {chrome_ws_url}")
        return chrome_ws_url
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return None

# ---------- CDP Команды ----------

class CDPClient:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.websocket = None
        self.session_id = None
        self.target_id = None
    
    async def connect(self):
        self.websocket = await websockets.connect(self.ws_url)
        logger.info("✅ Подключен к Chrome")
    
    async def send(self, method, params=None, session_id=None):
        msg = {
            "id": int(time.time() * 1000),
            "method": method,
            "params": params or {}
        }
        if session_id:
            msg["sessionId"] = session_id
        
        await self.websocket.send(json.dumps(msg))
        response = await self.websocket.recv()
        return json.loads(response)
    
    async def create_tab(self, url="about:blank"):
        response = await self.send("Target.createTarget", {"url": url})
        if "result" in response:
            self.target_id = response["result"]["targetId"]
            logger.info(f"✅ Вкладка: {self.target_id}")
            return self.target_id
        logger.error(f"❌ Ошибка: {response}")
        return None
    
    async def attach(self):
        response = await self.send("Target.attachToTarget", {"targetId": self.target_id})
        if "result" in response:
            self.session_id = response["result"]["sessionId"]
            logger.info(f"✅ Подключен: {self.session_id}")
            return self.session_id
        return None
    
    async def navigate(self, url):
        return await self.send("Page.navigate", {"url": url}, self.session_id)
    
    async def eval_js(self, code):
        response = await self.send("Runtime.evaluate", {"expression": code}, self.session_id)
        if "result" in response:
            return response["result"].get("result", {}).get("value", "")
        return None
    
    async def screenshot(self):
        response = await self.send("Page.captureScreenshot", {"format": "png"}, self.session_id)
        if "result" in response:
            return base64.b64decode(response["result"]["data"])
        return None
    
    async def close(self):
        if self.websocket:
            await self.websocket.close()

# ---------- Хранилище клиентов ----------

clients = {}

# ---------- Обработчик сообщений ----------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    
    user_id = update.message.from_user.id
    command = update.message.text.lower()
    
    await update.message.chat.send_action(action="typing")
    
    try:
        # Создаём клиента для пользователя
        if user_id not in clients:
            ws_url = get_websocket_url()
            if not ws_url:
                await update.message.reply_text("❌ Chrome не доступен")
                return
            
            client = CDPClient(ws_url)
            await client.connect()
            clients[user_id] = client
        
        client = clients[user_id]
        
        # Создаём вкладку если её нет
        if not client.target_id:
            await client.create_tab()
            await client.attach()
        
        # Google
        if "google" in command or "гугл" in command:
            await client.navigate("https://google.com")
            title = await client.eval_js("document.title")
            await update.message.reply_text(f"✅ Открыл Google\n📄 {title}")
            return
        
        # X.com
        if "x.com" in command or "twitter" in command or "твиттер" in command:
            await client.navigate("https://x.com")
            title = await client.eval_js("document.title")
            await update.message.reply_text(f"✅ Открыл X.com\n📄 {title}")
            return
        
        # Скриншот
        if "скриншот" in command or "screenshot" in command:
            img_data = await client.screenshot()
            if img_data:
                with open(f"screenshot_{user_id}.png", "wb") as f:
                    f.write(img_data)
                with open(f"screenshot_{user_id}.png", "rb") as photo:
                    await update.message.reply_photo(photo=photo)
            else:
                await update.message.reply_text("❌ Не удалось сделать скриншот")
            return
        
        # Любой URL
        if command.startswith("http"):
            await client.navigate(command)
            title = await client.eval_js("document.title")
            await update.message.reply_text(f"✅ Открыл\n📄 {title}")
            return
        
        # Помощь
        await update.message.reply_text(
            "🤖 **Управление браузером**\n\n"
            "Примеры:\n"
            "• Открой Google\n"
            "• Зайди в X.com\n"
            "• Сделай скриншот\n"
            "• https://youtube.com"
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 **Бот для управления браузером**\n\n"
        "Просто напиши что нужно сделать!\n"
        "• Открой Google\n"
        "• Зайди в X.com\n"
        "• Сделай скриншот\n"
        "• https://example.com"
    )

async def cdp_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        ws_url = get_websocket_url()
        if not ws_url:
            await update.message.reply_text("❌ Chrome не доступен")
            return
        
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Browser.getVersion"}))
            response = await ws.recv()
            data = json.loads(response)
            
            if "result" in data:
                await update.message.reply_text(f"✅ **Браузер активен**\n\n📦 {data['result'].get('product', 'Unknown')}")
            else:
                await update.message.reply_text("❌ Ошибка")
                
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

def main():
    logger.info("🚀 Запуск...")
    start_chrome()
    get_websocket_url()
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cdp", cdp_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()