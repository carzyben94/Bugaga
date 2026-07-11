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
        return response.json().get("webSocketDebuggerUrl")
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
        if not self.connected:
            self.ws = await websockets.connect(self.ws_url)
            self.connected = True
            logger.info("✅ WebSocket подключен")
            
            resp = await self.send("Target.createTarget", {"url": "about:blank"})
            if "result" in resp:
                self.target_id = resp["result"]["targetId"]
                logger.info(f"✅ Вкладка: {self.target_id}")
            
            if self.target_id:
                resp = await self.send("Target.attachToTarget", {"targetId": self.target_id})
                if "result" in resp:
                    self.session_id = resp["result"]["sessionId"]
                    logger.info(f"✅ Подключен к вкладке")
        
        return self.ws
    
    async def send(self, method, params=None):
        if not self.connected:
            await self.connect()
        
        self.msg_id += 1
        msg = {
            "id": self.msg_id,
            "method": method,
            "params": params or {}
        }
        
        if method.startswith("Page.") or method.startswith("Runtime.") or method.startswith("Network."):
            if self.session_id:
                msg["sessionId"] = self.session_id
        
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
        resp = await self.send("Page.navigate", {"url": url})
        time.sleep(3)
        return resp
    
    async def eval_js(self, code):
        """Выполнение JavaScript"""
        resp = await self.send("Runtime.evaluate", {"expression": code})
        if "result" in resp:
            return resp["result"].get("result", {}).get("value", "")
        return None
    
    async def screenshot(self):
        """Скриншот страницы"""
        try:
            # Проверяем, что страница загружена
            title = await self.eval_js("document.title")
            logger.info(f"📄 Текущая страница: {title}")
            
            # Если страница пустая, открываем Google
            if not title or title == "":
                logger.info("🌐 Открываю Google для скриншота...")
                await self.navigate("https://google.com")
            
            # Делаем скриншот
            resp = await self.send("Page.captureScreenshot", {
                "format": "png",
                "captureBeyondViewport": True,
                "fromSurface": True
            })
            
            logger.info(f"📸 Ответ CDP: {json.dumps(resp, indent=2)[:200]}")
            
            if "result" in resp and "data" in resp["result"]:
                logger.info("✅ Скриншот сделан")
                return base64.b64decode(resp["result"]["data"])
            else:
                logger.error(f"❌ Ошибка скриншота: {resp}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Screenshot error: {e}")
            return None
    
    async def close(self):
        if self.ws:
            await self.ws.close()
            self.connected = False

# ---------- Хранилище клиентов ----------

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
    Ты AI-агент для управления браузером через CDP (Chrome DevTools Protocol).
    
    Доступные действия (возвращай ТОЛЬКО JSON):
    {
        "action": "navigate|screenshot|js|click|fill|scroll|get_text",
        "params": {
            "url": "https://...",      # для navigate
            "code": "javascript code", # для js
            "selector": "css selector", # для click, fill, get_text
            "value": "text"           # для fill
        }
    }
    
    Примеры:
    1. Открыть Google: {"action": "navigate", "params": {"url": "https://google.com"}}
    2. Получить заголовок: {"action": "js", "params": {"code": "document.title"}}
    3. Сделать скриншот: {"action": "screenshot", "params": {}}
    4. Кликнуть на кнопку: {"action": "click", "params": {"selector": "button"}}
    5. Заполнить поле: {"action": "fill", "params": {"selector": "#email", "value": "test@mail.com"}}
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
        logger.info(f"Agnes ответ: {content[:200]}...")
        
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        
        return {"action": "js", "params": {"code": "document.title"}}
        
    except Exception as e:
        logger.error(f"Agnes error: {e}")
        return {"error": str(e)}

# ---------- Выполнение действий ----------

async def execute_action(client: CDPClient, action: dict) -> str:
    action_type = action.get("action")
    params = action.get("params", {})
    
    try:
        if action_type == "navigate":
            url = params.get("url", "https://google.com")
            await client.navigate(url)
            title = await client.eval_js("document.title")
            return f"✅ Открыл: {url}\n📄 {title}"
        
        elif action_type == "js":
            code = params.get("code", "document.title")
            result = await client.eval_js(code)
            return f"✅ JS результат:\n{result}"
        
        elif action_type == "screenshot":
            img_data = await client.screenshot()
            if img_data:
                with open("screenshot.png", "wb") as f:
                    f.write(img_data)
                return "screenshot"
            return "❌ Не удалось сделать скриншот"
        
        elif action_type == "click":
            selector = params.get("selector")
            code = f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.click();
                    return '✅ Кликнул: {selector}';
                }}
                return '❌ Элемент не найден: {selector}';
            }})()
            """
            result = await client.eval_js(code)
            return result
        
        elif action_type == "fill":
            selector = params.get("selector")
            value = params.get("value", "")
            code = f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.value = '{value}';
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    return '✅ Заполнил: {selector} = {value}';
                }}
                return '❌ Элемент не найден: {selector}';
            }})()
            """
            result = await client.eval_js(code)
            return result
        
        elif action_type == "get_text":
            selector = params.get("selector")
            code = f"""
            (function() {{
                const el = document.querySelector('{selector}');
                return el ? el.textContent : '❌ Элемент не найден: {selector}';
            }})()
            """
            result = await client.eval_js(code)
            return f"📄 Текст: {result}"
        
        elif action_type == "scroll":
            amount = params.get("amount", 500)
            code = f"window.scrollBy(0, {amount})"
            await client.eval_js(code)
            return f"✅ Прокрутил на {amount}px"
        
        else:
            return f"⚠️ Неизвестное действие: {action_type}"
            
    except Exception as e:
        logger.error(f"Execute error: {e}")
        return f"❌ Ошибка выполнения: {str(e)}"

# ---------- Прямые команды (запасной план) ----------

async def execute_command(client: CDPClient, command: str) -> str:
    cmd = command.lower()
    
    if "google" in cmd or "гугл" in cmd:
        await client.navigate("https://google.com")
        title = await client.eval_js("document.title")
        return f"✅ Открыл Google\n📄 {title}"
    
    if "x.com" in cmd or "twitter" in cmd or "твиттер" in cmd:
        await client.navigate("https://x.com")
        title = await client.eval_js("document.title")
        return f"✅ Открыл X.com\n📄 {title}"
    
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
    
    if "заголовок" in cmd or "title" in cmd:
        title = await client.eval_js("document.title")
        return f"📄 Заголовок: {title}"
    
    if "текст" in cmd or "читай" in cmd:
        text = await client.eval_js("document.body.innerText.slice(0, 500)")
        return f"📄 Текст:\n{text}..."
    
    return """
🤖 **Управление браузером**

Примеры:
• "Открой Google" — открыть Google
• "Зайди в X.com" — открыть X (Twitter)
• "Сделай скриншот" — скриншот страницы
• "https://example.com" — открыть любой URL
• "Заголовок" — показать заголовок
• "Текст" — показать текст страницы
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
        
        # Сначала пробуем Agnes
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
        
        # Если Agnes не сработал, используем прямые команды
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
        "🤖 **AI-агент для управления браузером**\n\n"
        "Просто напиши что нужно сделать!\n\n"
        "Примеры:\n"
        "• Открой Google\n"
        "• Зайди в X.com\n"
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
                    f"📦 {data['result'].get('product', 'Unknown')}\n"
                    f"🔌 Порт: 9222\n"
                    f"📊 Статус: Готов"
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