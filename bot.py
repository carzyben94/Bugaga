import os
import logging
import json
import subprocess
import time
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters, MessageHandler
import websockets
import re
import base64

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

AGNES_API_KEY = os.getenv("AGNES_API_KEY")
AGNES_API_URL = os.getenv("AGNES_API_URL", "https://api.agnes.ai/v1/chat/completions")

CHROME_PATH = "/usr/bin/google-chrome"
chrome_ws_url = None

# ---------- Запуск Chrome ----------

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

def get_websocket_url():
    """Получает WebSocket URL для Chrome"""
    global chrome_ws_url
    try:
        response = requests.get("http://localhost:9222/json/version")
        data = response.json()
        chrome_ws_url = data.get("webSocketDebuggerUrl")
        logger.info(f"✅ WebSocket URL: {chrome_ws_url}")
        return chrome_ws_url
    except Exception as e:
        logger.error(f"Ошибка получения WebSocket URL: {e}")
        return None

# ---------- CDP Команды ----------

async def cdp_send(method: str, params: dict = None, session_id: str = None):
    """Отправляет команду в Chrome через CDP"""
    global chrome_ws_url
    
    if not chrome_ws_url:
        chrome_ws_url = get_websocket_url()
        if not chrome_ws_url:
            raise Exception("Chrome WebSocket URL не получен")
    
    try:
        async with websockets.connect(chrome_ws_url) as websocket:
            message = {
                "id": int(time.time() * 1000),
                "method": method,
                "params": params or {}
            }
            if session_id:
                message["sessionId"] = session_id
            
            logger.info(f"📤 Отправка: {method}")
            await websocket.send(json.dumps(message))
            
            response = await websocket.recv()
            data = json.loads(response)
            logger.info(f"📥 Ответ: {json.dumps(data, indent=2)[:500]}")
            return data
            
    except Exception as e:
        logger.error(f"❌ CDP ошибка: {e}")
        return {"error": str(e)}

async def create_tab(url: str = "about:blank"):
    """Создаёт новую вкладку"""
    response = await cdp_send("Target.createTarget", {"url": url})
    
    if "result" in response:
        target_id = response["result"].get("targetId")
        if target_id:
            logger.info(f"✅ Создана вкладка: {target_id}")
            return target_id
    
    logger.error(f"❌ Не удалось создать вкладку: {response}")
    return None

async def attach_to_page(page_id: str):
    """Подключается к странице"""
    response = await cdp_send("Target.attachToTarget", {"targetId": page_id})
    
    if "result" in response:
        session_id = response["result"].get("sessionId")
        if session_id:
            logger.info(f"✅ Подключен к странице: {session_id}")
            return session_id
    
    logger.error(f"❌ Не удалось подключиться: {response}")
    return None

async def navigate_to(page_id: str, session_id: str, url: str):
    """Переходит по URL"""
    response = await cdp_send("Page.navigate", {"url": url}, session_id)
    
    if "result" in response:
        frame_id = response["result"].get("frameId")
        logger.info(f"✅ Навигация на {url}, frameId: {frame_id}")
        return True
    
    logger.error(f"❌ Ошибка навигации: {response}")
    return False

async def evaluate_js(session_id: str, expression: str):
    """Выполняет JavaScript на странице"""
    response = await cdp_send(
        "Runtime.evaluate",
        {"expression": expression},
        session_id
    )
    
    if "result" in response:
        result = response["result"].get("result", {})
        value = result.get("value", result.get("description", "undefined"))
        return value
    
    logger.error(f"❌ JS ошибка: {response}")
    return f"Ошибка: {response}"

async def take_screenshot(session_id: str):
    """Делает скриншот"""
    response = await cdp_send("Page.captureScreenshot", {"format": "png"}, session_id)
    
    if "result" in response:
        data = response["result"].get("data")
        if data:
            return base64.b64decode(data)
    
    logger.error(f"❌ Screenshot ошибка: {response}")
    return None

# ---------- Прямое выполнение команд ----------

async def execute_command(command: str, page_id: str, session_id: str) -> str:
    """Выполняет команду напрямую"""
    
    command_lower = command.lower()
    
    # Открыть Google
    if "google" in command_lower or "гугл" in command_lower:
        success = await navigate_to(page_id, session_id, "https://google.com")
        if success:
            title = await evaluate_js(session_id, "document.title")
            return f"✅ Открыл Google\n📄 {title}"
        return "❌ Не удалось открыть Google"
    
    # Открыть X
    if "x.com" in command_lower or "twitter" in command_lower or "твиттер" in command_lower:
        success = await navigate_to(page_id, session_id, "https://x.com")
        if success:
            title = await evaluate_js(session_id, "document.title")
            return f"✅ Открыл X.com\n📄 {title}"
        return "❌ Не удалось открыть X.com"
    
    # Скриншот
    if "скриншот" in command_lower or "screenshot" in command_lower:
        img_data = await take_screenshot(session_id)
        if img_data:
            with open("screenshot.png", "wb") as f:
                f.write(img_data)
            return "✅ Скриншот сделан!"
        return "❌ Не удалось сделать скриншот"
    
    # Поиск
    if "найди" in command_lower or "поиск" in command_lower:
        query = command.replace("найди", "").replace("поиск", "").strip()
        if query:
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            success = await navigate_to(page_id, session_id, search_url)
            if success:
                return f"✅ Ищу: {query}\n🔍 Открыл страницу поиска"
        return "❌ Не удалось выполнить поиск"
    
    # Заголовок
    if "заголовок" in command_lower or "title" in command_lower:
        title = await evaluate_js(session_id, "document.title")
        return f"📄 Заголовок: {title}"
    
    # Помощь
    return """
❌ Не понял команду.

Попробуйте:
• "Открой Google"
• "Зайди в X.com"
• "Сделай скриншот"
• "Найди погоду в Москве"
• "Что на странице?"
"""

# ---------- Agnes AI ----------

async def ask_agnes(prompt: str) -> dict:
    """Отправляет запрос к Agnes API"""
    
    if not AGNES_API_KEY:
        return {"error": "AGNES_API_KEY не установлен"}
    
    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json"
    }
    
    system_prompt = """
    Ты агент для управления браузером.
    Отвечай ТОЛЬКО JSON с действиями.
    
    Примеры:
    {"action": "navigate", "params": {"url": "https://google.com"}}
    {"action": "screenshot", "params": {}}
    {"action": "js", "params": {"code": "document.title"}}
    """
    
    data = {
        "model": "agnes-v1",
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
        result = response.json()
        
        content = result["choices"][0]["message"]["content"]
        
        # Пробуем извлечь JSON
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        
        return {"error": "Не JSON ответ", "raw": content}
            
    except Exception as e:
        logger.error(f"Agnes API error: {e}")
        return {"error": str(e)}

async def process_agent_response(response: dict, page_id: str, session_id: str) -> str:
    """Обрабатывает ответ агента"""
    
    if "error" in response:
        return f"❌ Ошибка агента: {response['error']}"
    
    action = response.get("action")
    params = response.get("params", {})
    
    if action == "navigate":
        url = params.get("url")
        success = await navigate_to(page_id, session_id, url)
        if success:
            return f"✅ Перешёл на {url}"
        return "❌ Не удалось перейти"
    
    elif action == "screenshot":
        img_data = await take_screenshot(session_id)
        if img_data:
            with open("screenshot.png", "wb") as f:
                f.write(img_data)
            return "✅ Скриншот сделан!"
        return "❌ Не удалось сделать скриншот"
    
    elif action == "js":
        code = params.get("code", "")
        result = await evaluate_js(session_id, code)
        return f"✅ Результат: {result}"
    
    else:
        return f"⚠️ Неизвестное действие: {action}"

# ---------- Обработчик сообщений ----------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает сообщения"""
    
    if not update.message or not update.message.text:
        return
    
    user_message = update.message.text
    
    await update.message.chat.send_action(action="typing")
    
    try:
        # Создаём вкладку
        page_id = await create_tab()
        if not page_id:
            await update.message.reply_text("❌ Не удалось создать вкладку")
            return
        
        session_id = await attach_to_page(page_id)
        if not session_id:
            await update.message.reply_text("❌ Не удалось подключиться к странице")
            return
        
        # Пробуем Agnes
        if AGNES_API_KEY:
            response = await ask_agnes(user_message)
            if "action" in response:
                result = await process_agent_response(response, page_id, session_id)
                await update.message.reply_text(result)
                return
        
        # Если Agnes не сработал, используем прямые команды
        result = await execute_command(user_message, page_id, session_id)
        await update.message.reply_text(result)
            
    except Exception as e:
        logger.error(f"Handle error: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ---------- Команды ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 **AI-агент для управления браузером**\n\n"
        "Просто напиши что нужно сделать!\n\n"
        "Примеры:\n"
        "• Открой Google\n"
        "• Зайди в X.com\n"
        "• Сделай скриншот\n"
        "• Найди погоду в Москве\n\n"
        "/cdp - статус браузера"
    )

async def cdp_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Статус браузера"""
    try:
        ws_url = get_websocket_url()
        if not ws_url:
            await update.message.reply_text("❌ Chrome не доступен")
            return
        
        async with websockets.connect(ws_url) as websocket:
            await websocket.send(json.dumps({
                "id": 1,
                "method": "Browser.getVersion"
            }))
            
            response = await websocket.recv()
            data = json.loads(response)
            
            if "result" in data:
                version = data["result"].get("product", "Unknown")
                status_text = f"""✅ **Браузер активен**

📦 Версия: {version}
🔌 Порт: 9222
📊 Статус: Готов к работе"""
                
                await update.message.reply_text(status_text)
            else:
                await update.message.reply_text(f"❌ Не удалось получить статус: {data}")
                
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ---------- Main ----------

def main() -> None:
    if not start_chrome():
        logger.warning("⚠️ Chrome не запустился")
    
    get_websocket_url()
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cdp", cdp_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()