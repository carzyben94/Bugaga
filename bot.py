import os
import subprocess
import asyncio
import json
import re
import time
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
AGNES_API_URL = os.environ.get("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")
AI_MODEL = "agnes-2.0-flash"

os.environ["BU_CDP_URL"] = "http://localhost:9222"

def check_browser():
    try:
        with httpx.Client() as client:
            response = client.get("http://localhost:9222/json/version", timeout=3.0)
            return response.status_code == 200
    except:
        return False

def ensure_browser():
    if check_browser():
        print("Браузер уже запущен")
        return True
    print("Запускаем браузер...")
    chrome_path = "/usr/bin/chromium"
    cmd = [
        chrome_path,
        "--headless",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--remote-debugging-port=9222",
        "--remote-debugging-address=0.0.0.0",
        "--user-data-dir=/tmp/chrome-profile",
        "about:blank"
    ]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for i in range(30):
        time.sleep(1)
        if check_browser():
            print(f"Браузер запущен! (через {i+1} сек)")
            return True
        print(f"Ожидание... {i+1}/30")
    print("Не удалось запустить браузер")
    return False

async def run_harness(code: str) -> tuple[str, str]:
    env = os.environ.copy()
    env["BU_CDP_URL"] = "http://localhost:9222"
    process = await asyncio.create_subprocess_exec(
        "browser-harness",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env
    )
    stdout, stderr = await process.communicate(code.encode())
    return stdout.decode(), stderr.decode()

async def execute_browser_code(code: str) -> tuple[str, bool]:
    try:
        code = re.sub(r'^import\s+\w+.*$', '', code, flags=re.MULTILINE)
        code = re.sub(r'^from\s+\w+.*import.*$', '', code, flags=re.MULTILINE)
        code = '\n'.join([line for line in code.split('\n') if line.strip()])
        if not any(h in code for h in ['goto_url', 'page_info', 'capture_screenshot', 'js', 'cdp', 'new_tab', 'wait_for_load', 'click_at_xy']):
            return code, True
        stdout, stderr = await run_harness(code)
        if stderr:
            return f"Ошибка: {stderr[:500]}", False
        if stdout:
            return stdout[:4000], True
        return "Выполнено успешно", True
    except Exception as e:
        return f"Ошибка выполнения: {str(e)[:500]}", False

async def ask_agnes(messages: list[dict]) -> str:
    if not AGNES_API_KEY:
        return "Ошибка: AGNES_API_KEY не задан."
    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": AI_MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 2000
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(AGNES_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            return "Неожиданный формат ответа"
    except Exception as e:
        return f"Ошибка LLM: {str(e)[:200]}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Агент с browser-harness\n\n"
        "Команды:\n"
        "/ask <запрос> - выполнить задачу\n"
        "/status - статус системы\n"
        "/debug - диагностика"
    )

async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Пример: /ask покажи заголовок example.com")
        return
    user_query = " ".join(context.args)
    status_msg = await update.message.reply_text("Думаю над задачей...")
    try:
        messages = [
            {"role": "system", "content": "Ты — ИИ-агент, управляющий браузером. Пиши код с хелперами: goto_url, page_info, capture_screenshot, js. ВСЕГДА возвращай код в ```python. НЕ используй import."},
            {"role": "user", "content": user_query}
        ]
        response = await ask_agnes(messages)
        if "```python" in response:
            code_match = re.search(r'```python\n(.*?)\n```', response, re.DOTALL)
            code = code_match.group(1) if code_match else response
            await status_msg.edit_text("Выполняю код...")
            result, success = await execute_browser_code(code)
            if success:
                await status_msg.edit_text("Готово!")
                await update.message.reply_text(f"Результат:\n{result}")
            else:
                await update.message.reply_text(f"Ошибка:\n{result}")
        else:
            await status_msg.edit_text("Ответ:")
            await update.message.reply_text(response[:4000])
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)[:200]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    browser_ok = check_browser()
    await update.message.reply_text(f"Браузер: {'работает' if browser_ok else 'не отвечает'}")

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = "info = page_info(); print(info)"
    stdout, stderr = await run_harness(code)
    await update.message.reply_text(f"Диагностика:\n{stdout[:4000] if stdout else stderr[:4000]}")

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
    if not ensure_browser():
        print("Браузер не запустился")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("debug", debug))
    print("Агент запускается...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()