import os
import logging
import json
import subprocess
import time
import requests
import re
import base64
import asyncio
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

# ---------- Логирование ----------

LOG_FILE = "bot_logs.txt"

class FileLogger:
    def __init__(self, filename=LOG_FILE):
        self.filename = filename
        with open(self.filename, 'w', encoding='utf-8') as f:
            f.write(f"=== Логи бота ===\n")
            f.write(f"Время запуска: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
    
    def log(self, message, level="INFO"):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(self.filename, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")

file_logger = FileLogger()

# ---------- Chrome ----------

def start_chrome():
    try:
        file_logger.log("Запуск Chrome...")
        result = subprocess.run(["pgrep", "-f", "google-chrome"], capture_output=True, text=True)
        if result.stdout:
            file_logger.log("✅ Chrome уже запущен")
            return True
        
        subprocess.Popen([
            CHROME_PATH,
            "--headless=new",
            "--remote-debugging-port=9222",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--user-data-dir=/tmp/chrome-profile",
            "--window-size=1920,1080"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        
        time.sleep(5)
        file_logger.log("✅ Chrome запущен")
        return True
    except Exception as e:
        file_logger.log(f"❌ Ошибка: {e}", "ERROR")
        return False

def get_page_ws_url():
    try:
        response = requests.get("http://localhost:9222/json")
        pages = response.json()
        for page in pages:
            if page.get("type") == "page":
                ws_url = page.get("webSocketDebuggerUrl")
                file_logger.log(f"✅ WebSocket: {ws_url}")
                return ws_url
        return None
    except Exception as e:
        file_logger.log(f"❌ Ошибка: {e}", "ERROR")
        return None

def create_page():
    try:
        response = requests.get("http://localhost:9222/json/new?about:blank")
        data = response.json()
        ws_url = data.get("webSocketDebuggerUrl")
        file_logger.log(f"✅ Создана страница: {ws_url}")
        return ws_url
    except Exception as e:
        file_logger.log(f"❌ Ошибка: {e}", "ERROR")
        return None

# ---------- CDP Client ----------

class CDPClient:
    def __init__(self):
        self.ws = None
        self.connected = False
        self.msg_id = 0
        self.user_id = None
        self.pending_responses = {}  # Ожидаемые ответы
    
    async def connect(self):
        if self.connected:
            return True
        
        file_logger.log(f"Подключение для пользователя {self.user_id}")
        
        ws_url = get_page_ws_url()
        if not ws_url:
            ws_url = create_page()
        
        if not ws_url:
            file_logger.log("❌ Не удалось получить WebSocket URL", "ERROR")
            return False
        
        try:
            self.ws = await websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=60,
                close_timeout=10
            )
            self.connected = True
            file_logger.log("✅ WebSocket подключен")
            
            # Включаем домены
            await self.send("Page.enable", {})
            await self.send("Runtime.enable", {})
            file_logger.log("✅ Page.enable и Runtime.enable")
            
            # Открываем страницу
            await self.navigate("https://google.com")
            
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Connect error: {e}", "ERROR")
            return False
    
    async def send(self, method, params=None):
        """Отправка команды с ожиданием ответа"""
        if not self.connected:
            await self.connect()
        
        self.msg_id += 1
        msg_id = self.msg_id
        
        msg = {
            "id": msg_id,
            "method": method,
            "params": params or {}
        }
        
        try:
            # Отправляем запрос
            await self.ws.send(json.dumps(msg))
            file_logger.log(f"📤 {method} (id: {msg_id})")
            
            # Ждём ответ с правильным id
            while True:
                response = await asyncio.wait_for(self.ws.recv(), timeout=30)
                data = json.loads(response)
                
                # Проверяем, что это ответ на наш запрос (есть id)
                if data.get("id") == msg_id:
                    if "error" in data:
                        file_logger.log(f"❌ {method} error: {data['error']}", "ERROR")
                    else:
                        file_logger.log(f"📥 {method} (id: {msg_id}) - OK")
                    return data
                
                # Если это событие без id - игнорируем
                if "method" in data:
                    file_logger.log(f"📡 Событие: {data.get('method')}")
                    continue
                
                # Если id не совпадает - игнорируем
                if data.get("id") is not None:
                    file_logger.log(f"⚠️ Игнорируем ответ с id {data.get('id')}, ждём {msg_id}")
                    continue
                
        except asyncio.TimeoutError:
            file_logger.log(f"❌ {method} timeout", "ERROR")
            return {"error": "Timeout"}
        except Exception as e:
            file_logger.log(f"❌ {method} error: {e}", "ERROR")
            return {"error": str(e)}
    
    async def navigate(self, url):
        file_logger.log(f"🌐 Навигация на {url}")
        resp = await self.send("Page.navigate", {"url": url})
        
        # Ждём загрузки
        for i in range(10):
            await asyncio.sleep(1)
            title = await self.eval_js("document.title")
            if title and title != "":
                file_logger.log(f"📄 Страница загружена: {title}")
                break
        
        return resp
    
    async def eval_js(self, code):
        """Выполняет JavaScript"""
        resp = await self.send("Runtime.evaluate", {"expression": code})
        
        if "result" in resp:
            result_obj = resp["result"]
            if isinstance(result_obj, dict):
                if "result" in result_obj:
                    return result_obj["result"].get("value", "")
                elif "value" in result_obj:
                    return result_obj["value"]
        return None
    
    async def screenshot(self):
        """Делает скриншот страницы"""
        try:
            if not self.connected:
                await self.connect()
            
            # Проверяем страницу
            title = await self.eval_js("document.title")
            file_logger.log(f"📄 Текущий заголовок: {title}")
            
            if not title or title == "":
                file_logger.log("🌐 Открываю Google...")
                await self.navigate("https://google.com")
                await asyncio.sleep(2)
            
            # Делаем скриншот
            file_logger.log("📸 Делаю скриншот...")
            
            resp = await self.send("Page.captureScreenshot", {
                "format": "png",
                "captureBeyondViewport": True,
                "fromSurface": True
            })
            
            file_logger.log(f"📸 Ответ: {json.dumps(resp, indent=2)[:300]}")
            
            if "result" in resp and "data" in resp["result"]:
                file_logger.log("✅ Скриншот сделан")
                return base64.b64decode(resp["result"]["data"])
            
            # Пробуем без параметров
            file_logger.log("⚠️ Пробую без параметров...")
            resp2 = await self.send("Page.captureScreenshot", {})
            
            if "result" in resp2 and "data" in resp2["result"]:
                file_logger.log("✅ Скриншот сделан (2)")
                return base64.b64decode(resp2["result"]["data"])
            
            file_logger.log(f"❌ Ошибка скриншота: нет data", "ERROR")
            return None
                
        except Exception as e:
            file_logger.log(f"❌ Screenshot error: {e}", "ERROR")
            return None

# ---------- Хранилище ----------

clients = {}

# ---------- Agnes AI ----------

async def ask_agnes(prompt: str) -> dict:
    if not AGNES_API_KEY:
        return {"error": "AGNES_API_KEY не установлен"}
    
    file_logger.log(f"Запрос к Agnes: {prompt[:100]}...")
    
    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json"
    }
    
    system_prompt = """
    Ты AI-агент для управления браузером через CDP.
    Отвечай ТОЛЬКО JSON.
    Доступные действия:
    - navigate: {"action": "navigate", "params": {"url": "https://..."}}
    - screenshot: {"action": "screenshot", "params": {}}
    - js: {"action": "js", "params": {"code": "javascript"}}
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
        
        file_logger.log(f"Agnes ответ: {content[:200]}...")
        
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {"action": "js", "params": {"code": "document.title"}}
    except Exception as e:
        file_logger.log(f"Agnes error: {e}", "ERROR")
        return {"error": str(e)}

async def execute_action(client: CDPClient, action: dict) -> str:
    action_type = action.get("action")
    params = action.get("params", {})
    
    file_logger.log(f"Выполнение: {action_type}")
    
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
    file_logger.log(f"Прямая команда: {command[:100]}...")
    
    if "google" in cmd or "гугл" in cmd:
        await client.navigate("https://google.com")
        title = await client.eval_js("document.title")
        return f"✅ Открыл Google\n📄 {title}"
    
    if "ютуб" in cmd or "youtube" in cmd:
        await client.navigate("https://youtube.com")
        title = await client.eval_js("document.title")
        return f"✅ Открыл YouTube\n📄 {title}"
    
    if "скриншот" in cmd or "скрин" in cmd or "screenshot" in cmd:
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
    
    if "заголовок" in cmd or "title" in cmd:
        title = await client.eval_js("document.title")
        return f"📄 Заголовок: {title}"
    
    return """
🤖 **Управление браузером**

Примеры:
• Открой Google
• Зайди в ютуб
• Сделай скриншот
• https://example.com
"""

# ---------- Команды ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Управление браузером**\n\n"
        "Просто напиши что нужно сделать!\n\n"
        "Примеры:\n"
        "• Открой Google\n"
        "• Зайди в ютуб\n"
        "• Сделай скриншот\n"
        "• https://youtube.com\n\n"
        "Команды:\n"
        "/cdp - статус браузера\n"
        "/logs - получить логи\n"
        "/clear_logs - очистить логи"
    )

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"bot_logs_{time.strftime('%Y-%m-%d_%H-%M-%S')}.txt",
                    caption="📋 Логи бота"
                )
        else:
            await update.message.reply_text("❌ Файл логов не найден")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def clear_logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.write(f"=== Логи очищены ===\n")
            f.write(f"Время очистки: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
        await update.message.reply_text("✅ Логи очищены")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def cdp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        response = requests.get("http://localhost:9222/json")
        pages = response.json()
        
        status_text = f"✅ **Браузер активен**\n\n"
        status_text += f"📄 Страниц: {len(pages)}\n\n"
        
        for page in pages[:3]:
            title = page.get('title', 'без названия')[:30]
            url = page.get('url', '')[:40]
            status_text += f"• {title}\n  {url}\n\n"
        
        await update.message.reply_text(status_text)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ---------- Обработчик ----------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    user_id = update.message.from_user.id
    prompt = update.message.text
    
    file_logger.log(f"Сообщение от {user_id}: {prompt[:100]}...")
    
    await update.message.chat.send_action(action="typing")
    
    try:
        if user_id not in clients:
            client = CDPClient()
            client.user_id = user_id
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
                        file_logger.log("✅ Скриншот отправлен")
                else:
                    await update.message.reply_text(result)
                return
        
        # Прямые команды
        result = await execute_command(client, prompt)
        if result == "screenshot":
            with open("screenshot.png", "rb") as photo:
                await update.message.reply_photo(photo=photo)
                file_logger.log("✅ Скриншот отправлен")
        else:
            await update.message.reply_text(result)
            
    except Exception as e:
        file_logger.log(f"❌ Ошибка: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ---------- Main ----------

def main():
    print("🚀 Запуск бота...")
    file_logger.log("🚀 Запуск бота...")
    
    start_chrome()
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cdp", cdp))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("clear_logs", clear_logs_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен!")
    file_logger.log("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()