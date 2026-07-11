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
    
    async with websockets.connect(chrome_ws_url) as websocket:
        message = {
            "id": int(time.time() * 1000),
            "method": method,
            "params": params or {}
        }
        if session_id:
            message["sessionId"] = session_id
        
        await websocket.send(json.dumps(message))
        response = await websocket.recv()
        return json.loads(response)

async def create_tab(url: str = "about:blank"):
    """Создаёт новую вкладку"""
    response = await cdp_send("Target.createTarget", {"url": url})
    return response["result"]["targetId"]

async def attach_to_page(page_id: str):
    """Подключается к странице"""
    response = await cdp_send("Target.attachToTarget", {"targetId": page_id})
    return response["result"]["sessionId"]

async def evaluate_js(session_id: str, expression: str):
    """Выполняет JavaScript на странице"""
    response = await cdp_send(
        "Runtime.evaluate",
        {"expression": expression},
        session_id
    )
    
    if "result" in response:
        result = response["result"].get("result", {})
        return result.get("value", result.get("description", "undefined"))
    return f"❌ Ошибка: {response}"

# ---------- Прямое выполнение без Agnes (запасной план) ----------

async def execute_direct_command(command: str, page_id: str, session_id: str) -> str:
    """Выполняет команду напрямую, если Agnes не отвечает"""
    
    # Открыть Google
    if "google" in command.lower() or "гугл" in command.lower():
        await cdp_send("Page.navigate", {"url": "https://google.com"}, session_id)
        title = await evaluate_js(session_id, "document.title")
        return f"✅ Открыл Google\n📄 Заголовок: {title}"
    
    # Открыть X/Twitter
    if "x.com" in command.lower() or "twitter" in command.lower() or "твиттер" in command.lower():
        await cdp_send("Page.navigate", {"url": "https://x.com"}, session_id)
        title = await evaluate_js(session_id, "document.title")
        return f"✅ Открыл X.com\n📄 Заголовок: {title}"
    
    # Скриншот
    if "скриншот" in command.lower() or "screenshot" in command.lower():
        response = await cdp_send("Page.captureScreenshot", {"format": "png"}, session_id)
        if "result" in response:
            import base64
            img_data = base64.b64decode(response["result"]["data"])
            with open("screenshot.png", "wb") as f:
                f.write(img_data)
            return "✅ Скриншот сделан!"
        return "❌ Не удалось сделать скриншот"
    
    # Заголовок страницы
    if "заголовок" in command.lower() or "title" in command.lower():
        title = await evaluate_js(session_id, "document.title")
        return f"📄 Заголовок: {title}"
    
    # Поиск (прямая навигация)
    if "найди" in command.lower() or "поиск" in command.lower():
        # Извлекаем поисковый запрос
        query = command.replace("найди", "").replace("поиск", "").strip()
        if query:
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            await cdp_send("Page.navigate", {"url": search_url}, session_id)
            return f"✅ Ищу: {query}\n🔍 Открыл страницу поиска"
    
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
    Ты AI-агент для управления браузером через CDP.
    
    Инструменты:
    - exec_cdp(domain, command, params) - выполнить CDP команду
    - eval_js(code) - выполнить JavaScript
    
    ОТВЕЧАЙ ТОЛЬКО JSON:
    {
        "actions": [
            {"tool": "exec_cdp", "params": {"domain": "Page", "command": "navigate", "params": {"url": "https://google.com"}}}
        ]
    }
    
    Для простых команд используй eval_js:
    {"tool": "eval_js", "params": {"code": "document.title"}}
    """
    
    data = {
        "model": "agnes-v1",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 500
    }
    
    try:
        response = requests.post(AGNES_API_URL, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        content = result["choices"][0]["message"]["content"]
        
        # Пытаемся извлечь JSON
        try:
            # Ищем JSON в ответе
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        
        # Если не JSON, пробуем распарсить как простой текст
        return {"actions": [], "message": content}
            
    except Exception as e:
        logger.error(f"Agnes API error: {e}")
        return {"error": str(e)}

async def execute_tool(tool: str, params: dict, page_id: str, session_id: str) -> str:
    """Выполняет инструмент агента"""
    
    if tool == "exec_cdp":
        domain = params.get("domain")
        command = params.get("command")
        cmd_params = params.get("params", {})
        
        method = f"{domain}.{command}"
        
        try:
            response = await cdp_send(method, cmd_params, session_id)
            
            if "result" in response:
                result = json.dumps(response["result"], indent=2, ensure_ascii=False)
                return f"✅ {domain}.{command} выполнено"
            else:
                return f"❌ Ошибка: {response.get('error', {}).get('message', 'Неизвестная ошибка')}"
                
        except Exception as e:
            return f"❌ Ошибка: {str(e)}"
    
    elif tool == "eval_js":
        code = params.get("code", "")
        try:
            result = await evaluate_js(session_id, code)
            return f"✅ Результат: {result}"
        except Exception as e:
            return f"❌ Ошибка JS: {str(e)}"
    
    else:
        return f"⚠️ Неизвестный инструмент: {tool}"

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
        session_id = await attach_to_page(page_id)
        
        # Сначала пробуем Agnes
        response = await ask_agnes(user_message)
        
        # Если есть actions, выполняем их
        if "actions" in response and response["actions"]:
            results = []
            for action in response["actions"]:
                tool = action.get("tool")
                params = action.get("params", {})
                result = await execute_tool(tool, params, page_id, session_id)
                results.append(result)
            
            if results:
                await update.message.reply_text("\n\n".join(results))
                return
        
        # Если Agnes не сработал, используем прямые команды
        result = await execute_direct_command(user_message, page_id, session_id)
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
                await update.message.reply_text("❌ Не удалось получить статус")
                
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