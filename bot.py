import os
import logging
import json
import subprocess
import time
import requests
import re
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters, MessageHandler
import websockets

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

AGNES_API_KEY = os.getenv("AGNES_API_KEY")
AGNES_API_URL = os.getenv("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")

CHROME_PATH = "/usr/bin/google-chrome"

# ---------- Chrome ----------

def start_chrome():
    try:
        result = subprocess.run(["pgrep", "-f", "google-chrome"], capture_output=True, text=True)
        if result.stdout:
            logger.info("✅ Chrome уже запущен")
            return True
        
        subprocess.Popen([
            CHROME_PATH,
            "--headless",
            "--remote-debugging-port=9222",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--user-data-dir=/tmp/chrome-profile"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        
        time.sleep(5)
        logger.info("✅ Chrome запущен")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False

def get_ws_url():
    try:
        response = requests.get("http://localhost:9222/json/version")
        data = response.json()
        ws_url = data.get("webSocketDebuggerUrl")
        logger.info(f"✅ WebSocket URL: {ws_url}")
        return ws_url
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return None

# ---------- CDP Client ----------

class CDPClient:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.ws = None
        self.session_id = None
        self.target_id = None
        self.connected = False
        self.msg_id = 0
    
    async def connect(self):
        """Подключение к Chrome"""
        if self.connected:
            return True
        
        try:
            self.ws = await websockets.connect(self.ws_url)
            self.connected = True
            logger.info("✅ WebSocket подключен")
            
            # Создаём вкладку
            resp = await self._send("Target.createTarget", {"url": "about:blank"})
            if "result" in resp:
                self.target_id = resp["result"]["targetId"]
                logger.info(f"✅ Вкладка: {self.target_id}")
            
            # Подключаемся к вкладке
            resp = await self._send("Target.attachToTarget", {"targetId": self.target_id})
            if "result" in resp:
                self.session_id = resp["result"]["sessionId"]
                logger.info(f"✅ SessionId: {self.session_id}")
            
            # Включаем Page
            await self._send("Page.enable", {}, self.session_id)
            logger.info("✅ Page.enable")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Connect error: {e}")
            return False
    
    async def _send(self, method, params=None, session_id=None):
        """Отправка запроса"""
        self.msg_id += 1
        msg = {
            "id": self.msg_id,
            "method": method,
            "params": params or {}
        }
        
        if session_id:
            msg["sessionId"] = session_id
        
        try:
            await self.ws.send(json.dumps(msg))
            response = await self.ws.recv()
            data = json.loads(response)
            
            if "error" in data:
                logger.error(f"❌ {method}: {data['error']}")
            else:
                logger.info(f"✅ {method}")
            
            return data
        except Exception as e:
            logger.error(f"❌ Send error: {e}")
            return {"error": str(e)}
    
    async def navigate(self, url):
        """Переход по URL"""
        if not self.session_id:
            await self.connect()
        
        resp = await self._send("Page.navigate", {"url": url}, self.session_id)
        time.sleep(2)
        return resp
    
    async def eval_js(self, code):
        """Выполнение JavaScript"""
        if not self.session_id:
            await self.connect()
        
        resp = await self._send("Runtime.evaluate", {"expression": code}, self.session_id)
        if "result" in resp:
            return resp["result"].get("result", {}).get("value", "")
        return None
    
    async def screenshot(self):
        """Скриншот"""
        if not self.session_id:
            await self.connect()
        
        try:
            # Проверяем страницу
            title = await self.eval_js("document.title")
            logger.info(f"📄 Заголовок: {title}")
            
            if not title or title == "":
                logger.info("🌐 Открываю Google...")
                await self.navigate("https://google.com")
                time.sleep(2)
            
            # Скриншот
            resp = await self._send("Page.captureScreenshot", {
                "format": "png",
                "captureBeyondViewport": True
            }, self.session_id)
            
            if "result" in resp and "data" in resp["result"]:
                logger.info("✅ Скриншот сделан")
                return base64.b64decode(resp["result"]["data"])
            else:
                logger.error(f"❌ Ошибка: {resp}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Screenshot error: {e}")
            return None

# ---------- Хранилище ----------

clients = {}

# ---------- Agnes AI ----------

async def ask_agnes(prompt: str) -> dict:
    if not AGNES_API_KEY:
        return {"error": "AGNES_API_KEY не установлен"}
    
    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json"
    }
    
    system_prompt = """
    Ты AI-агент для управления браузером.
    Отвечай ТОЛЬКО JSON:
    {"action": "navigate|screenshot|js|click|fill", "params": {...}}
    """
    
    data = {
        "model": "agnes-2.0-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 300
    }
    
    try:
        response = requests.post(AGNES_API_URL, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {"action": "js", "params": {"code": "document.title"}}
    except Exception as e:
        logger.error(f"Agnes error: {e}")
        return {"error": str(e)}

async def execute_action(client: CDPClient, action: dict) -> str:
    action_type = action.get("action")
    params = action.get("params", {})
    
    if action_type == "navigate":
        url = params.get("url", "https://google.com")
        await client.navigate(url)
        title = await client.eval_js("document.title")
        return f"✅ Открыл: {url}\n📄 {title}"
    
    elif action_type == "screenshot":
        img_data = await client.screenshot()
        if img_data:
            with open("screenshot.png", "wb") as f:
                f.write(img_data)
            return "screenshot"
        return "❌ Не удалось сделать скриншот"
    
    elif action_type == "js":
        code = params.get("code", "document.title")
        result = await client.eval_js(code)
        return f"✅ Результат: {result}"
    
    else:
        return f"⚠️ Неизвестно: {action_type}"

# ---------- Прямые команды ----------

async def execute_command(client: CDPClient, command: str) -> str:
    cmd = command.lower()
    
    if "google" in cmd or "гугл" in cmd:
        await client.navigate("https://google.com")
        title = await client.eval_js("document.title")
        return f"✅ Открыл Google\n📄 {title}"
    
    if "скриншот" in cmd or "screenshot" in cmd:
        img_data = await client.screenshot()
        if img_data:
            with open("screenshot.png", "wb") as f:
                f.write(img_data)
            return "screenshot"
        return "❌ Не удалось сделать скриншот"
    
    if cmd.startswith("http"):
        await client.navigate(cmd)
        title = await client.eval_js("document.title")
        return f"✅ Открыл\n📄 {title}"
    
    return """
🤖 **Управление браузером**

Примеры:
• Открой Google
• Сделай скриншот
• https://example.com
"""

# ---------- Обработчик ----------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    user_id = update.message.from_user.id
    prompt = update.message.text
    
    await update.message.chat.send_action(action="typing")
    
    try:
        if user_id not in clients:
            ws_url = get_ws_url()
            if not ws_url:
                await update.message.reply_text("❌ Chrome не доступен")
                return
            
            client = CDPClient(ws_url)
            await client.connect()
            clients[user_id] = client
        
        client = clients[user_id]
        
        # Пробуем Agnes
        if AGNES_API_KEY:
            response = await ask_agnes(prompt)
            if "error" not in response:
                result = await execute_action(client, response)
                if result == "screenshot":
                    with open("screenshot.png", "rb") as photo:
                        await update.message.reply_photo(photo=photo)
                else:
                    await update.message.reply_text(result)
                return
        
        # Прямые команды
        result = await execute_command(client, prompt)
        if result == "screenshot":
            with open("screenshot.png", "rb") as photo:
                await update.message.reply_photo(photo=photo)
        else:
            await update.message.reply_text(result)
            
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ---------- Команды ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Управление браузером**\n\n"
        "Просто напиши что нужно сделать!\n\n"
        "Примеры:\n"
        "• Открой Google\n"
        "• Сделай скриншот\n"
        "• https://youtube.com\n\n"
        "/cdp - статус браузера"
    )

async def cdp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ws_url = get_ws_url()
    if not ws_url:
        await update.message.reply_text("❌ Chrome не доступен")
        return
    
    try:
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Browser.getVersion"}))
            resp = await ws.recv()
            data = json.loads(resp)
            
            if "result" in data:
                await update.message.reply_text(
                    f"✅ **Браузер активен**\n\n"
                    f"📦 {data['result'].get('product', 'Unknown')}"
                )
            else:
                await update.message.reply_text("❌ Ошибка")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ---------- Main ----------

def main():
    logger.info("🚀 Запуск бота...")
    
    if not start_chrome():
        logger.warning("⚠️ Chrome не запустился")
    
    get_ws_url()
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cdp", cdp))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()