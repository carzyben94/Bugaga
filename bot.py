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

# ---------- Логирование в файл ----------

LOG_FILE = "bot_logs.txt"

class FileLogger:
    """Класс для записи логов в файл"""
    def __init__(self, filename=LOG_FILE):
        self.filename = filename
        # Очищаем файл при старте
        with open(self.filename, 'w', encoding='utf-8') as f:
            f.write(f"=== Логи бота ===\n")
            f.write(f"Время запуска: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
    
    def log(self, message, level="INFO"):
        """Запись сообщения в файл"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(self.filename, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")
    
    def get_logs(self, lines=100):
        """Получение последних строк лога"""
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                content = f.read()
                # Возвращаем последние строки
                lines_list = content.split('\n')
                if len(lines_list) > lines:
                    return '\n'.join(lines_list[-lines:])
                return content
        except Exception as e:
            return f"❌ Ошибка чтения логов: {e}"

# Создаём экземпляр логгера
file_logger = FileLogger()

# Перехватываем логи через декоратор
def log_to_file(func):
    """Декоратор для логирования вызовов функций"""
    async def wrapper(*args, **kwargs):
        func_name = func.__name__
        file_logger.log(f"Вызвана функция: {func_name}")
        try:
            result = await func(*args, **kwargs)
            file_logger.log(f"Функция {func_name} выполнена успешно")
            return result
        except Exception as e:
            file_logger.log(f"Ошибка в {func_name}: {e}", "ERROR")
            raise
    return wrapper

# ---------- Chrome ----------

def start_chrome():
    try:
        file_logger.log("Запуск Chrome...")
        result = subprocess.run(["pgrep", "-f", "google-chrome"], capture_output=True, text=True)
        if result.stdout:
            file_logger.log("✅ Chrome уже запущен")
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
        file_logger.log("✅ Chrome запущен")
        logger.info("✅ Chrome запущен")
        return True
    except Exception as e:
        file_logger.log(f"❌ Ошибка запуска Chrome: {e}", "ERROR")
        logger.error(f"❌ Ошибка: {e}")
        return False

def get_ws_url():
    try:
        response = requests.get("http://localhost:9222/json/version")
        data = response.json()
        ws_url = data.get("webSocketDebuggerUrl")
        file_logger.log(f"✅ WebSocket URL получен: {ws_url}")
        logger.info(f"✅ WebSocket URL: {ws_url}")
        return ws_url
    except Exception as e:
        file_logger.log(f"❌ Ошибка получения WebSocket URL: {e}", "ERROR")
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
        self.user_id = None
    
    async def connect(self):
        if self.connected:
            return True
        
        file_logger.log(f"Подключение к Chrome для пользователя {self.user_id}")
        
        try:
            self.ws = await websockets.connect(self.ws_url)
            self.connected = True
            file_logger.log("✅ WebSocket подключен")
            logger.info("✅ WebSocket подключен")
            
            resp = await self._send("Target.createTarget", {"url": "about:blank"})
            if "result" in resp:
                self.target_id = resp["result"]["targetId"]
                file_logger.log(f"✅ Вкладка создана: {self.target_id}")
                logger.info(f"✅ Вкладка: {self.target_id}")
            
            resp = await self._send("Target.attachToTarget", {"targetId": self.target_id})
            if "result" in resp:
                self.session_id = resp["result"]["sessionId"]
                file_logger.log(f"✅ SessionId: {self.session_id}")
                logger.info(f"✅ SessionId: {self.session_id}")
            
            await self._send("Page.enable", {}, self.session_id)
            file_logger.log("✅ Page.enable")
            
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Connect error: {e}", "ERROR")
            logger.error(f"❌ Connect error: {e}")
            return False
    
    async def _send(self, method, params=None, session_id=None):
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
                file_logger.log(f"❌ {method}: {data['error']}", "ERROR")
                logger.error(f"❌ {method}: {data['error']}")
            else:
                file_logger.log(f"✅ {method}")
                logger.info(f"✅ {method}")
            
            return data
        except Exception as e:
            file_logger.log(f"❌ Send error: {e}", "ERROR")
            logger.error(f"❌ Send error: {e}")
            return {"error": str(e)}
    
    async def navigate(self, url):
        file_logger.log(f"Навигация на {url} для пользователя {self.user_id}")
        
        if not self.session_id:
            await self.connect()
        
        resp = await self._send("Page.navigate", {"url": url}, self.session_id)
        time.sleep(2)
        return resp
    
    async def eval_js(self, code):
        if not self.session_id:
            await self.connect()
        
        resp = await self._send("Runtime.evaluate", {"expression": code}, self.session_id)
        if "result" in resp:
            return resp["result"].get("result", {}).get("value", "")
        return None
    
    async def screenshot(self):
        if not self.session_id:
            await self.connect()
        
        try:
            title = await self.eval_js("document.title")
            file_logger.log(f"📄 Заголовок: {title}")
            logger.info(f"📄 Заголовок: {title}")
            
            if not title or title == "":
                file_logger.log("🌐 Открываю Google...")
                await self.navigate("https://google.com")
                time.sleep(2)
            
            resp = await self._send("Page.captureScreenshot", {
                "format": "png",
                "captureBeyondViewport": True
            }, self.session_id)
            
            if "result" in resp and "data" in resp["result"]:
                file_logger.log("✅ Скриншот сделан")
                logger.info("✅ Скриншот сделан")
                return base64.b64decode(resp["result"]["data"])
            else:
                file_logger.log(f"❌ Ошибка скриншота: {resp}", "ERROR")
                logger.error(f"❌ Ошибка скриншота: {resp}")
                return None
                
        except Exception as e:
            file_logger.log(f"❌ Screenshot error: {e}", "ERROR")
            logger.error(f"❌ Screenshot error: {e}")
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
        
        file_logger.log(f"Agnes ответ: {content[:100]}...")
        
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {"action": "js", "params": {"code": "document.title"}}
    except Exception as e:
        file_logger.log(f"Agnes error: {e}", "ERROR")
        logger.error(f"Agnes error: {e}")
        return {"error": str(e)}

async def execute_action(client: CDPClient, action: dict) -> str:
    action_type = action.get("action")
    params = action.get("params", {})
    
    file_logger.log(f"Выполнение действия: {action_type}")
    
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

# ---------- Команда /logs ----------

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет файл с логами"""
    user_id = update.message.from_user.id
    
    # Проверяем, что пользователь админ (можно добавить свой ID)
    # ADMIN_IDS = [123456789]  # Раскомментировать и добавить свои ID
    
    # if user_id not in ADMIN_IDS:
    #     await update.message.reply_text("⛔ У вас нет доступа к логам")
    #     return
    
    try:
        # Проверяем размер файла
        if os.path.exists(LOG_FILE):
            file_size = os.path.getsize(LOG_FILE)
            file_logger.log(f"Запрос логов от пользователя {user_id}, размер: {file_size} байт")
            
            if file_size > 50 * 1024 * 1024:  # 50MB
                await update.message.reply_text("❌ Файл логов слишком большой (>50MB)")
                return
            
            # Отправляем файл
            with open(LOG_FILE, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"bot_logs_{time.strftime('%Y-%m-%d_%H-%M-%S')}.txt",
                    caption="📋 Логи бота"
                )
            
            file_logger.log(f"✅ Логи отправлены пользователю {user_id}")
        else:
            await update.message.reply_text("❌ Файл логов не найден")
            
    except Exception as e:
        file_logger.log(f"❌ Ошибка отправки логов: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ---------- Команда /clear_logs ----------

async def clear_logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очищает файл логов"""
    user_id = update.message.from_user.id
    
    # Проверяем права (можно добавить проверку на админа)
    
    try:
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.write(f"=== Логи очищены ===\n")
            f.write(f"Время очистки: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
        
        file_logger.log(f"✅ Логи очищены пользователем {user_id}")
        await update.message.reply_text("✅ Логи очищены")
        
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
            ws_url = get_ws_url()
            if not ws_url:
                await update.message.reply_text("❌ Chrome не доступен")
                return
            
            client = CDPClient(ws_url)
            client.user_id = user_id
            await client.connect()
            clients[user_id] = client
        
        client = clients[user_id]
        
        if AGNES_API_KEY:
            response = await ask_agnes(prompt)
            if "error" not in response:
                result = await execute_action(client, response)
                if result == "screenshot":
                    with open("screenshot.png", "rb") as photo:
                        await update.message.reply_photo(photo=photo)
                        file_logger.log(f"✅ Отправлен скриншот пользователю {user_id}")
                else:
                    await update.message.reply_text(result)
                return
        
        result = await execute_command(client, prompt)
        if result == "screenshot":
            with open("screenshot.png", "rb") as photo:
                await update.message.reply_photo(photo=photo)
                file_logger.log(f"✅ Отправлен скриншот пользователю {user_id}")
        else:
            await update.message.reply_text(result)
            
    except Exception as e:
        file_logger.log(f"❌ Ошибка обработки: {e}", "ERROR")
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
        "Команды:\n"
        "/cdp - статус браузера\n"
        "/logs - получить логи\n"
        "/clear_logs - очистить логи"
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
    print("🚀 Запуск бота...")
    file_logger.log("🚀 Запуск бота...")
    
    if not start_chrome():
        file_logger.log("⚠️ Chrome не запустился", "WARNING")
        print("⚠️ Chrome не запустился")
    
    get_ws_url()
    
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