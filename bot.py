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

AGNES_API_KEY = os.getenv("AGNES_API_KEY")
AGNES_API_URL = os.getenv("AGNES_API_URL", "https://api.agnes.ai/v1/chat/completions")

CHROME_PATH = "/usr/bin/google-chrome"
chrome_ws_url = None
cdp_protocol = None
cdp_full_docs = ""

# ---------- Функции запуска Chrome ----------

def start_chrome():
    """Запускает Chrome в фоновом режиме"""
    try:
        # Проверяем, не запущен ли уже Chrome
        result = subprocess.run(
            ["pgrep", "-f", "google-chrome"],
            capture_output=True,
            text=True
        )
        
        if result.stdout:
            logger.info("✅ Chrome уже запущен")
            return True
        
        # Запускаем Chrome
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

def load_cdp_protocol():
    """Загружает полную спецификацию CDP"""
    global cdp_protocol, cdp_full_docs
    
    try:
        response = requests.get("http://localhost:9222/json/protocol")
        cdp_protocol = response.json()
        
        # Краткая информация о доменах
        domains = cdp_protocol.get("domains", [])
        cdp_full_docs = f"📚 CDP содержит {len(domains)} доменов.\n\n"
        
        # Список всех доменов и их команд (сжато для токенов)
        for domain in domains[:15]:  # Ограничиваем для размера
            domain_name = domain.get("domain", "")
            commands = [cmd.get("name") for cmd in domain.get("commands", [])[:10]]
            cdp_full_docs += f"**{domain_name}**: {', '.join(commands)}\n"
        
        logger.info(f"✅ Загружена CDP спецификация: {len(domains)} доменов")
        return cdp_protocol
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки CDP протокола: {e}")
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
    return "❌ Ошибка выполнения JS"

# ---------- Agnes AI ----------

async def ask_agnes(prompt: str, context: str = "") -> dict:
    """Отправляет запрос к Agnes API"""
    
    if not AGNES_API_KEY:
        raise ValueError("AGNES_API_KEY не установлен!")
    
    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json"
    }
    
    system_prompt = f"""
    Ты AI-агент с ПОЛНЫМ контролем над браузером через CDP (Chrome DevTools Protocol).
    
    Доступные инструменты:
    1. **exec_cdp(domain, command, params)** - выполнить ЛЮБУЮ CDP команду
    2. **eval_js(js_code)** - выполнить произвольный JavaScript
    
    Ты можешь делать ВСЁ в браузере!
    
    ВСЕГДА используй exec_cdp для навигации: Page.navigate
    ВСЕГДА используй eval_js для взаимодействия с DOM
    
    {cdp_full_docs}
    
    ОТВЕЧАЙ В ФОРМАТЕ JSON:
    {{
        "reasoning": "что я делаю",
        "actions": [
            {{"tool": "exec_cdp", "params": {{"domain": "Page", "command": "navigate", "params": {{"url": "https://google.com"}}}}}},
            {{"tool": "eval_js", "params": {{"code": "document.title"}}}}
        ]
    }}
    """
    
    data = {
        "model": "agnes-v1",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Контекст: {context}\nЗапрос: {prompt}"}
        ],
        "temperature": 0.3,
        "max_tokens": 1000
    }
    
    try:
        response = requests.post(AGNES_API_URL, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = response.json()
        
        content = result["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except:
            return {"reasoning": "прямой ответ", "actions": [], "message": content}
            
    except Exception as e:
        logger.error(f"Agnes API error: {e}")
        return {"reasoning": "ошибка", "actions": [], "error": str(e)}

async def execute_tool(tool: str, params: dict, page_id: str, session_id: str) -> str:
    """Выполняет инструмент агента"""
    
    if tool == "exec_cdp":
        domain = params.get("domain")
        command = params.get("command")
        cmd_params = params.get("params", {})
        
        method = f"{domain}.{command}"
        
        try:
            if page_id:
                session_id = await attach_to_page(page_id)
                response = await cdp_send(method, cmd_params, session_id)
            else:
                response = await cdp_send(method, cmd_params)
            
            if "result" in response:
                result = json.dumps(response["result"], indent=2, ensure_ascii=False)
                return f"✅ {domain}.{command} выполнено: {result[:500]}"
            else:
                return f"❌ Ошибка: {response.get('error', {}).get('message', 'Неизвестная ошибка')}"
                
        except Exception as e:
            return f"❌ Ошибка выполнения {domain}.{command}: {str(e)}"
    
    elif tool == "eval_js":
        code = params.get("code", "")
        try:
            result = await evaluate_js(session_id, code)
            return f"✅ JS результат: {result}"
        except Exception as e:
            return f"❌ Ошибка JS: {str(e)}"
    
    else:
        return f"⚠️ Неизвестный инструмент: {tool}"

# ---------- Обработчики ----------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает сообщения"""
    
    if not update.message or not update.message.text:
        return
    
    user_message = update.message.text
    
    await update.message.chat.send_action(action="typing")
    
    try:
        page_id = await create_tab()
        session_id = await attach_to_page(page_id)
        
        response = await ask_agnes(user_message)
        
        results = []
        
        if response.get("reasoning"):
            results.append(f"🧠 {response['reasoning']}")
        
        for action in response.get("actions", []):
            tool = action.get("tool")
            params = action.get("params", {})
            
            result = await execute_tool(tool, params, page_id, session_id)
            results.append(result)
        
        if results:
            await update.message.reply_text("\n\n".join(results))
        else:
            await update.message.reply_text("✅ Готово!")
            
    except Exception as e:
        logger.error(f"Handle error: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 **AI-агент с полным контролем браузера**\n\n"
        "Просто напиши что нужно сделать!\n\n"
        "Примеры:\n"
        "• Открой Google и найди погоду\n"
        "• Зайди в X.com\n"
        "• Сделай скриншот\n"
        "• Напиши сообщение\n\n"
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
🧠 Агент: Agnes AI
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
    load_cdp_protocol()
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cdp", cdp_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()