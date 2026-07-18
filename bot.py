import os
import sys
import time
import logging
import base64
import re
import asyncio
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================================
# 1. ИМПОРТ ИЗ BROWSER-HARNESS
# ============================================================

sys.path.insert(0, "browser-harness/src")

# helpers.py - только то, что есть!
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
    start_remote_daemon,
    stop_remote_daemon,
)

# admin.py - управление daemon
from browser_harness.admin import (
    ensure_daemon,
    daemon_alive,
    restart_daemon,
    run_doctor,
    run_update,
)

# daemon.py - класс BrowserDaemon
from browser_harness.daemon import BrowserDaemon

# ============================================================
# 2. НАСТРОЙКА
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(
            "https://apihub.agnes-ai.com/v1/chat/completions",
            headers=headers,
            json=payload
        )
        return response.json()["choices"][0]["message"]["content"]

# ============================================================
# 4. ВЫПОЛНЕНИЕ КОДА
# ============================================================

def execute_code(code):
    """Выполняет код напрямую с доступом ко ВСЕМ хелперам"""
    try:
        globals_dict = {
            # helpers.py
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
            'start_remote_daemon': start_remote_daemon,
            'stop_remote_daemon': stop_remote_daemon,
            
            # admin.py
            'ensure_daemon': ensure_daemon,
            'daemon_alive': daemon_alive,
            'restart_daemon': restart_daemon,
            'run_doctor': run_doctor,
            'run_update': run_update,
            
            # daemon.py
            'BrowserDaemon': BrowserDaemon,
            
            # Встроенные функции
            'print': print,
            '__builtins__': __builtins__,
        }
        
        exec(code, globals_dict)
        
        if 'result' in globals_dict:
            return str(globals_dict['result']), None
        
        return "✅ Выполнено успешно", None
    except Exception as e:
        return None, str(e)

# ============================================================
# 5. КОМАНДЫ БОТА
# ============================================================

async def start(update, context):
    await update.message.reply_text(
        "/ask <запрос> — задать задачу агенту\n"
        "/screenshot — скриншот google.com"
    )

async def screenshot(update, context):
    msg = await update.message.reply_text("📸 Делаю скриншот...")
    try:
        new_tab("https://google.com")
        wait_for_load()
        time.sleep(2)
        ensure_real_tab()

        result = cdp("Page.captureScreenshot", format="jpeg", quality=85, captureBeyondViewport=False)
        screenshot_b64 = result.get("data")

        if not screenshot_b64:
            raise ValueError("Скриншот пустой")

        if ',' in screenshot_b64:
            screenshot_b64 = screenshot_b64.split(',', 1)[1]
        screenshot_b64 = screenshot_b64.strip()

        missing_padding = len(screenshot_b64) % 4
        if missing_padding:
            screenshot_b64 += '=' * (4 - missing_padding)

        img_bytes = base64.b64decode(screenshot_b64)

        if len(img_bytes) < 1000:
            raise ValueError("Скриншот слишком маленький")

        await update.message.reply_photo(photo=img_bytes, caption="📸 Скриншот")
        await msg.edit_text("✅ Скриншот отправлен!")

    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def ask(update, context):
    if not context.args:
        await update.message.reply_text("Пример: /ask сделай скриншот google.com")
        return

    user_query = " ".join(context.args)
    status_msg = await update.message.reply_text("🤔 Думаю...")

    try:
        system_prompt = """
You are a browser agent that controls a real browser via browser-harness.

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

Rules:
- NEVER use selectors for clicks — only coordinates from the screenshot
- First navigation is ALWAYS new_tab()
- ALWAYS wait_for_load() after navigation
- Screenshots are your primary way to understand the page
- For screenshots use cdp("Page.captureScreenshot", {"format": "png", "quality": 80})
- Use js() only for reading DOM data, never for clicks
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
                await status_msg.edit_text(f"❌ Ошибка: {error[:500]}")
            else:
                await status_msg.edit_text(f"✅ Результат:\n{output[:4000]}")
        else:
            await status_msg.edit_text(response[:4000])

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# 6. ЗАПУСК
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("screenshot", screenshot))

    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()