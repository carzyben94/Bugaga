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

sys.path.insert(0, "browser-harness/src")

from browser_harness.helpers import *
from browser_harness.admin import ensure_daemon

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

os.environ["BU_CDP_URL"] = "http://localhost:9222"
ensure_daemon()
logger.info("✅ Браузер готов")

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

async def run_harness(code):
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

async def start(update, context):
    await update.message.reply_text(
        "/ask <запрос> — задать задачу агенту"
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
Ты — ИИ-агент, управляющий браузером через browser-harness.

ОСНОВНЫЕ ПРИНЦИПЫ:
1. Скриншоты — первый шаг. Всегда используй CDP-метод для скриншотов.
2. Клики по координатам: Скриншот -> координаты -> click_at_xy(x, y) -> скриншот для проверки. НЕ используй селекторы!
3. Навигация: Первая навигация — new_tab(url). После навигации — wait_for_load().
4. Ввод текста: type_text(text) + press_key("Enter").

ХЕЛПЕРЫ (не требуют импорта):
new_tab(url) - открыть новую вкладку (ПЕРВАЯ НАВИГАЦИЯ)
goto_url(url) - перейти по URL в текущей вкладке
wait_for_load() - дождаться загрузки
page_info() - получить информацию о странице
capture_screenshot(max_dim=800) - сделать скриншот (base64)
click_at_xy(x, y) - кликнуть по координатам
type_text(text) - ввести текст
press_key(key) - нажать клавишу
scroll(x, y) - прокрутить страницу
js(script) - выполнить JavaScript (ТОЛЬКО ДЛЯ ЧТЕНИЯ ДАННЫХ)
cdp(method, params) - отправить CDP-команду
ensure_real_tab() - проверить, что мы в реальной вкладке

Для скриншотов ВСЕГДА используй CDP:
result = cdp("Page.captureScreenshot", {"format": "jpeg", "quality": 85})

Для кликов:
1. capture_screenshot() — увидеть страницу
2. click_at_xy(x, y) — клик по координатам
3. capture_screenshot() — проверить результат

ФОРМАТ ВЫВОДА:
Для скриншотов:
{
  "action": "screenshot_taken",
  "screenshot": "base64-строка",
  "source": "Название с эмодзи",
  "note": "Описание"
}

КОГДА НЕ НУЖЕН БРАУЗЕР:
- Простые вопросы (погода, курс, факты) — отвечай текстом БЕЗ кода

ВАЖНО:
- Клики — ТОЛЬКО по координатам, НЕ через селекторы
- ПЕРВАЯ навигация — ТОЛЬКО new_tab()
- После навигации ВСЕГДА wait_for_load()
- Скриншот — ПЕРВЫЙ шаг в любой задаче с браузером
- Для скриншотов — CDP
- ВСЕГДА оборачивай код в ```python ... ```
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
            stdout, stderr = await run_harness(code)

            if stderr:
                await status_msg.edit_text(f"❌ Ошибка: {stderr[:500]}")
            else:
                await status_msg.edit_text(f"✅ Результат:\n{stdout[:4000]}")
        else:
            await status_msg.edit_text(response[:4000])

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("screenshot", screenshot))  # скрыта, но работает

    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()