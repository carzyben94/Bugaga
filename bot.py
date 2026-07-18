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
    chrome_path = "/usr/bin/chromium"
    if check_browser():
        print("Браузер уже запущен")
        return True
    print("Запускаем браузер...")
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
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )
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

SYSTEM_PROMPT = """
Ты — ИИ-агент, который управляет браузером через browser-harness.

ВАЖНО: НЕ ИСПОЛЬЗУЙ import В КОДЕ! Хелперы уже доступны глобально.

Доступные хелперы:
- new_tab(url) - открыть новую вкладку
- wait_for_load() - дождаться загрузки
- page_info() - получить информацию о странице (возвращает dict)
- capture_screenshot(max_dim=1800) - сделать скриншот (возвращает bytes)
- click_at_xy(x, y) - кликнуть по координатам
- type_text(text) - ввести текст
- press_key(key) - нажать клавишу
- scroll(x, y) - прокрутить страницу
- js(script) - выполнить JavaScript
- goto_url(url) - перейти по URL
- cdp(method, params) - отправить CDP-команду

Правильный пример (обязательно в маркдауне):
```python
goto_url("https://example.com")
wait_for_load()
info = page_info()
print(f"Заголовок: {info['title']}")
```

Неправильный пример (НЕ ИСПОЛЬЗУЙ):

```python
import json
from browser_harness import ...
```

Правила:

1. ВСЕГДА возвращай код в формате python ... 
2. Для получения заголовка используй: info = page_info(); print(info['title'])
3. Для скриншота: data = capture_screenshot(); print(len(data))
4. ВСЕГДА возвращай результат через print()
5. НЕ используй import, НЕ пытайся парсить JSON вручную
6. НЕ выводи просто текст с кодом — ВСЕГДА оборачивай в ```python
   """

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
async with httpx.AsyncClient(timeout=60.0) as client:
response = await client.post(AGNES_API_URL, headers=headers, json=payload)
response.raise_for_status()
data = response.json()
if "choices" in data and len(data["choices"]) > 0:
return data["choices"][0]["message"]["content"]
return "Неожиданный формат ответа"
except Exception as e:
return f"Ошибка LLM: {str(e)[:200]}"

async def execute_agent_code(code: str) -> tuple[str, bool]:
try:
code_match = re.search(r'python\n(.*?)\n', code, re.DOTALL)
if code_match:
code = code_match.group(1)
else:
if 'goto_url' in code or 'page_info' in code or 'new_tab' in code:
pass
else:
return code, True
code = re.sub(r'^import\s+\w+.*$', '', code, flags=re.MULTILINE)
        code = re.sub(r'^from\s+\w+.*import.*$', '', code, flags=re.MULTILINE)
code = '\n'.join([line for line in code.split('\n') if line.strip()])
if not any(h in code for h in ['new_tab', 'page_info', 'capture_screenshot', 'click_at_xy', 'js', 'cdp', 'goto_url', 'wait_for_load']):
return code, True
stdout, stderr = await run_harness(code)
if stderr:
return f"Ошибка: {stderr[:500]}", False
if stdout:
return stdout[:4000], True
return "Выполнено успешно", True
except Exception as e:
return f"Ошибка выполнения: {str(e)[:500]}", False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text(
"Агент с browser-harness\n\n"
"Я умею управлять браузером по твоим командам.\n"
"Просто напиши, что нужно сделать.\n\n"
"Команды:\n"
"/ask <запрос> - задать задачу\n"
"/status - статус системы\n"
"/debug - диагностика"
)

async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not context.args:
await update.message.reply_text(
"ИИ-агент с browser-harness\n\n"
"Примеры запросов:\n"
"/ask покажи заголовок example.com\n"
"/ask сделай скриншот github.com\n"
"/ask найди контакты на сайте"
)
return
user_query = " ".join(context.args)
status_msg = await update.message.reply_text("Думаю над задачей...")
try:
messages = [
{"role": "system", "content": SYSTEM_PROMPT},
{"role": "user", "content": user_query}
]
response = await ask_agnes(messages)
if "python" in response or 'goto_url' in response or 'page_info' in response:
            await status_msg.edit_text("Выполняю код...")
            result, success = await execute_agent_code(response)
            if success:
                await status_msg.edit_text("Готово!")
                await update.message.reply_text(f"Результат:\n{result}")
            else:
                await status_msg.edit_text("Исправляю ошибку...")
                error_messages = messages + [
                    {"role": "assistant", "content": response},
                    {"role": "user", "content": f"Код выдал ошибку. Исправь. Не используй import! ВСЕГДА оборачивай в python\nОшибка: {result}"}
]
fixed_response = await ask_agnes(error_messages)
if "```python" in fixed_response:
result2, success2 = await execute_agent_code(fixed_response)
if success2:
await status_msg.edit_text("Исправлено!")
await update.message.reply_text(f"Результат:\n{result2}")
else:
await update.message.reply_text(f"Не удалось исправить:\n{result2}")
else:
await update.message.reply_text(f"Агент не смог исправить ошибку:\n{result}")
else:
await status_msg.edit_text("Ответ:")
await update.message.reply_text(response[:4000])
except Exception as e:
await update.message.reply_text(f"Ошибка: {str(e)[:200]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
browser_ok = check_browser()
status_text = "работает" if browser_ok else "не отвечает"
try:
process = await asyncio.create_subprocess_exec(
"browser-harness", "--version",
stdout=asyncio.subprocess.PIPE,
stderr=asyncio.subprocess.PIPE
)
stdout, _ = await process.communicate()
version = stdout.decode().strip() if stdout else "неизвестно"
cli_status = f"{version}"
except:
cli_status = "не найден"
llm_status = "подключена" if AGNES_API_KEY else "не задан ключ"
await update.message.reply_text(
f"Браузер: {status_text}\n"
f"CLI browser-harness: {cli_status}\n"
f"Agnes AI: {llm_status}"
)

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
code = """
info = page_info()
print(f"Страница: {info.get('title', 'нет заголовка')}")
print(f"URL: {info.get('url', 'нет URL')}")
"""
stdout, stderr = await run_harness(code)
msg = "Диагностика:\n\n"
if stdout:
msg += stdout
if stderr:
msg += f"\nОшибки: {stderr[:200]}"
await update.message.reply_text(msg[:4000])

def main():
if not TELEGRAM_TOKEN:
raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
if not ensure_browser():
print("Браузер не запустился")
app = Application.builder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("ask", ask))
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("status", status))
app.add_handler(CommandHandler("debug", debug))
print("Агент запускается...")
print("Команды: /ask, /status, /debug")
app.run_polling(allowed_updates=Update.ALL_TYPES)

if name == "main":
main()