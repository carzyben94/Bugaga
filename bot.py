import os
import sys
import time
import logging
import base64
import re
import asyncio
import io
import json
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

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
logger = logging.getLogger(__name__)

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
)

from browser_harness.admin import ensure_daemon

# ============================================================
# 2. НАСТРОЙКА
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

os.environ["BU_CDP_URL"] = "http://localhost:9222"
ensure_daemon()
logger.info("✅ Браузер готов")

# ============================================================
# 3. ЗАПРОС К AGNES AI
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
# 4. ВЫПОЛНЕНИЕ КОДА
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
            'print': print,
            '__builtins__': __builtins__,
        }
        
        exec(code, globals_dict)
        
        sys.stdout = old_stdout
        output = stdout_buffer.getvalue()
        
        if output:
            logger.info(f"📤 ВЫВОД КОДА:\n{output}")
            return output.strip(), None
        elif 'result' in globals_dict:
            result = str(globals_dict['result'])
            logger.info(f"📤 РЕЗУЛЬТАТ: {result}")
            return result, None
        
        logger.warning("⚠️ Код выполнен, но нет вывода")
        return "⚠️ Код выполнен, но нет вывода. Добавьте print() в код.", None
    except Exception as e:
        logger.error(f"❌ Ошибка выполнения: {e}")
        return None, str(e)

# ============================================================
# 5. КОМАНДЫ БОТА
# ============================================================

async def start(update, context):
    logger.info(f"👤 {update.effective_user.username} вызвал /start")
    await update.message.reply_text(
        "/ask <запрос> — задать задачу агенту\n"
        "/log — скачать файл логов"
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
You are a browser agent that controls a real browser via browser-harness.

🚨 CRITICAL RULES:
1. ALWAYS use print() to output the result. Without print(), the user sees nothing.
2. ALWAYS call ensure_real_tab() BEFORE any cdp() or capture_screenshot().
3. For PRICES and DATA — use js() to read from DOM, NOT screenshots!
4. Screenshots are ONLY for when user explicitly asks "screenshot".

OUTPUT FORMAT:
- Use print() to output the result
- Make it readable for the user
- For prices: include product name + price
- For lists: use numbered items or bullet points
- Be clear and concise

Core workflow (screenshots first):
1. capture_screenshot() to see the current page
2. Use the screenshot to pick pixel coordinates
3. click_at_xy(x, y) — no selector hunting!
4. capture_screenshot() to verify

Navigation:
- First navigation ALWAYS new_tab(url)
- Subsequent navigation goto_url(url)
- Always wait_for_load() after navigation

Helpers available:
new_tab(url), goto_url(url), wait_for_load(), page_info(),
capture_screenshot(max_dim=1800), click_at_xy(x, y), type_text(text),
press_key(key), scroll(x, y), js(script), cdp(method, params), ensure_real_tab()

WHEN TO USE WHAT:
- PRICES / DATA: js() → print()
- SCREENSHOTS: only when user explicitly asks
- CLICKS: click_at_xy(x, y) with coordinates from screenshot
- SEARCH: type_text() + press_key("Enter")

EXAMPLES:

✅ CORRECT (prices via js() with readable output):
new_tab("https://apple.com/de")
wait_for_load()
prices = js("""
  const items = document.querySelectorAll('.price, .product-price, [class*="price"]');
  Array.from(items).map(el => el.textContent.trim());
""")
for price in prices:
    print(f"• {price}")

✅ CORRECT (screenshot when asked):
new_tab("https://google.com")
wait_for_load()
ensure_real_tab()
result = capture_screenshot(max_dim=1800)
print(result)

RULES:
- NEVER use selectors for clicks — only coordinates from the screenshot
- First navigation is ALWAYS new_tab()
- ALWAYS wait_for_load() after navigation
- ALWAYS use print() to output the result
- ALWAYS call ensure_real_tab() before capture_screenshot() or cdp()
- Wrap code in ```python ... ```
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
            
            output, error = execute_code(code)

            if error:
                logger.error(f"❌ Ошибка выполнения для {username}: {error[:200]}")
                await status_msg.edit_text(f"❌ Ошибка: {error[:500]}")
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
# 6. ЗАПУСК
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("log", log))

    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()