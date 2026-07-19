import os
import sys
import stat
import time
import logging
import base64
import re
import asyncio
import io
import json
import httpx
import warnings
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================================
# ПОЛНОСТЬЮ ОТКЛЮЧАЕМ ЛИШНИЕ ЛОГИ
# ============================================================

warnings.filterwarnings("ignore")

# ============================================================
# ДОБАВЛЯЕМ AGENT_WORKSPACE В PYTHON PATH
# ============================================================

agent_workspace = "browser-harness/agent-workspace"
sys.path.insert(0, agent_workspace)

# ============================================================
# НАСТРОЙКА ПРАВ ДЛЯ AGENT_HELPERS.PY
# ============================================================

helpers_file = os.path.join(agent_workspace, "agent_helpers.py")

os.makedirs(agent_workspace, exist_ok=True)

if not os.path.exists(helpers_file):
    with open(helpers_file, "w") as f:
        f.write('"""Agent-editable browser helpers."""\n')

os.chmod(agent_workspace, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
os.chmod(helpers_file, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)

# ============================================================
# ВКЛЮЧАЕМ НАВЫКИ
# ============================================================

os.environ["BH_DOMAIN_SKILLS"] = "1"
os.environ["BH_AGENT_WORKSPACE"] = "browser-harness/agent-workspace"

# ============================================================
# 0. ЛОГИ
# ============================================================

LOGS_DIR = '/app/logs'
os.makedirs(LOGS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'bot.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Отключаем все лишние логи
logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("telegram").setLevel(logging.CRITICAL)
logging.getLogger("telegram.ext").setLevel(logging.CRITICAL)

logger = logging.getLogger(__name__)
logger.info(f"✅ agent_workspace: {agent_workspace}")
logger.info(f"✅ helpers_file: {helpers_file}")

# ============================================================
# 1. ИМПОРТ ИЗ BROWSER-HARNESS
# ============================================================

sys.path.insert(0, "browser-harness/src")

from browser_harness.helpers import (
    new_tab,
    goto_url,
    wait_for_load,
    page_info,
    capture_screenshot,
    click_at_xy,
    type_text,
    press_key,
    scroll,
    js,
    cdp,
    ensure_real_tab,
    wait_for_element,
    list_tabs,
    current_tab,
    close_tab,
)

from browser_harness.admin import ensure_daemon

# ============================================================
# 2. УСТАНОВКА КУК ЧЕРЕЗ WEBSOCKETS
# ============================================================

try:
    from cookies import COOKIES
    import websockets
    import json
    
    async def set_cookies_async():
        """Устанавливает куки через websockets (асинхронно)"""
        try:
            import httpx
            
            # Получаем список вкладок
            resp = httpx.get("http://localhost:9222/json/list", timeout=5.0)
            pages = resp.json()
            
            if not pages:
                logger.error("❌ Нет активных вкладок")
                return False
            
            ws_url = pages[0]["webSocketDebuggerUrl"]
            logger.info("🔗 Подключаюсь к WebSocket...")
            
            async with websockets.connect(ws_url) as websocket:
                cmd = {
                    "id": 1,
                    "method": "Network.setCookies",
                    "params": {"cookies": COOKIES}
                }
                await websocket.send(json.dumps(cmd))
                response = json.loads(await websocket.recv())
                
                if "error" in response:
                    logger.error(f"❌ CDP ошибка: {response['error']}")
                    return False
                
                logger.info(f"🍪 Установлено {len(COOKIES)} кук через WebSocket")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка установки кук: {e}")
            return False
    
    def set_cookies_global():
        """Использует существующий event loop (без создания нового)"""
        try:
            # Получаем существующий loop
            loop = asyncio.get_running_loop()
            # Создаём задачу в существующем loop
            future = asyncio.run_coroutine_threadsafe(set_cookies_async(), loop)
            return future.result(timeout=10)
        except RuntimeError:
            # Если loop нет — запускаем новый
            return asyncio.run(set_cookies_async())
        except Exception as e:
            logger.error(f"❌ Ошибка установки кук: {e}")
            return False
            
except ImportError:
    logger.warning("⚠️ websockets не установлен")
    COOKIES = []
    def set_cookies_global():
        return False

# ============================================================
# 3. НАСТРОЙКА
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

os.environ["BU_CDP_URL"] = "http://localhost:9222"
ensure_daemon()
logger.info("✅ Браузер готов")

# Устанавливаем куки
set_cookies_global()

# ============================================================
# 4. ЗАПРОС К AGNES AI
# ============================================================

async def ask_agnes(messages):
    logger.info("=" * 60)
    logger.info("📤 ОТПРАВКА В AGNES AI:")
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        logger.info(f"  [{role}]: {content[:500]}..." if len(content) > 500 else f"  [{role}]: {content}")
    logger.info("=" * 60)
    
    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "agnes-2.0-flash",
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 2000
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                "https://apihub.agnes-ai.com/v1/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            logger.info("=" * 60)
            logger.info("📥 ОТВЕТ ОТ AGNES AI:")
            logger.info(f"  {content}")
            logger.info("=" * 60)
            
            return content
    except Exception as e:
        logger.error(f"❌ Ошибка Agnes AI: {e}")
        return f"Ошибка LLM: {str(e)[:200]}"

# ============================================================
# 5. ВЫПОЛНЕНИЕ КОДА
# ============================================================

def execute_code(code):
    logger.info(f"⚙️ ВЫПОЛНЕНИЕ КОДА:\n{code}")
    try:
        stdout_buffer = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = stdout_buffer
        
        globals_dict = {
            'new_tab': new_tab,
            'goto_url': goto_url,
            'wait_for_load': wait_for_load,
            'page_info': page_info,
            'capture_screenshot': capture_screenshot,
            'click_at_xy': click_at_xy,
            'type_text': type_text,
            'press_key': press_key,
            'scroll': scroll,
            'js': js,
            'cdp': cdp,
            'ensure_real_tab': ensure_real_tab,
            'ensure_daemon': ensure_daemon,
            'wait_for_element': wait_for_element,
            'list_tabs': list_tabs,
            'current_tab': current_tab,
            'close_tab': close_tab,
            'set_cookies': set_cookies_global,
            'print': print,
            '__builtins__': __builtins__,
        }
        
        exec(code, globals_dict)
        
        sys.stdout = old_stdout
        output = stdout_buffer.getvalue()
        
        if output:
            logger.info(f"📤 ВЫВОД КОДА:\n{output}")
            return output.strip(), True
        elif 'result' in globals_dict:
            result = str(globals_dict['result'])
            logger.info(f"📤 РЕЗУЛЬТАТ: {result}")
            return result, True
        
        logger.warning("⚠️ Код выполнен, но нет вывода")
        return "⚠️ Код выполнен, но нет вывода. Добавьте print() в код.", False
    except Exception as e:
        logger.error(f"❌ Ошибка выполнения: {e}")
        return None, False

# ============================================================
# 6. КОМАНДЫ БОТА
# ============================================================

async def start(update, context):
    logger.info(f"👤 {update.effective_user.username} вызвал /start")
    await update.message.reply_text(
        "/ask <запрос> — задать задачу агенту\n"
        "/log — скачать файл логов\n"
        "/skills — список навыков агента"
    )

async def log(update, context):
    logger.info(f"👤 {update.effective_user.username} вызвал /log")
    try:
        log_file = os.path.join(LOGS_DIR, 'bot.log')
        if not os.path.exists(log_file):
            await update.message.reply_text("📭 Лог-файл не найден")
            return
        
        with open(log_file, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename='bot.log',
                caption=f"📋 Логи бота ({os.path.getsize(log_file)} байт)"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def skills(update, context):
    """Показывает список доступных навыков"""
    logger.info(f"👤 {update.effective_user.username} вызвал /skills")
    try:
        skills_dir = os.path.join(
            os.environ.get("BH_AGENT_WORKSPACE", "browser-harness/agent-workspace"),
            "domain-skills"
        )
        
        if not os.path.exists(skills_dir):
            await update.message.reply_text("📭 Папка с навыками не найдена")
            return
        
        skills_list = []
        for domain in os.listdir(skills_dir):
            domain_path = os.path.join(skills_dir, domain)
            if os.path.isdir(domain_path):
                for f in os.listdir(domain_path):
                    if f.endswith(".md") or f.endswith(".txt"):
                        skills_list.append(f"{domain}/{f}")
        
        if skills_list:
            msg = "🧠 **Доступные навыки:**\n\n"
            for skill in skills_list[:20]:
                msg += f"• `{skill}`\n"
            if len(skills_list) > 20:
                msg += f"\n... и ещё {len(skills_list) - 20}"
            await update.message.reply_text(msg, parse_mode='Markdown')
        else:
            await update.message.reply_text("🧠 Навыков пока нет. Агент создаст их по мере работы.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def ask(update, context):
    if not context.args:
        await update.message.reply_text("Пример: /ask сделай скриншот google.com")
        return

    user_query = " ".join(context.args)
    username = update.effective_user.username or "unknown"
    logger.info(f"👤 {username} запросил: {user_query}")
    
    status_msg = await update.message.reply_text("🤔 Думаю...")

    try:
        system_prompt = """
Browser agent. Goal: get result and save as skill.

USE DIRECTLY (no classes, no objects):
new_tab, goto_url, wait_for_load, ensure_real_tab, capture_screenshot,
js, click_at_xy, type_text, press_key, scroll, page_info, cdp, wait_for_element.

DO NOT create classes or objects. Use helpers directly.
Check agent_helpers.py → create helper if missing → try until works → save → print().

Rules: new_tab first, wait_for_load after navigation, ensure_real_tab before CDP,
no yield/async, no selector clicks (use coordinates), print() output.
Wrap code in ```python ... ```.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ]

        response = await ask_agnes(messages)

        if "```python" in response:
            code_match = re.search(r'```python\n(.*?)\n```', response, re.DOTALL)
            code = code_match.group(1) if code_match else response

            await status_msg.edit_text("⚙️ Выполняю код...")
            
            output, success = execute_code(code)

            if not success:
                await status_msg.edit_text(f"❌ {output}")
            else:
                logger.info(f"✅ Успешное выполнение для {username}")
                await status_msg.edit_text(f"✅ Результат:\n{output[:4000]}")
        else:
            logger.info(f"💬 Ответ без кода для {username}: {response[:100]}...")
            await status_msg.edit_text(response[:4000])

    except Exception as e:
        logger.error(f"❌ Ошибка в /ask для {username}: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# 7. ЗАПУСК
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("log", log))
    app.add_handler(CommandHandler("skills", skills))

    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()