import os
import subprocess
import asyncio
import json
import re
import time
import base64
import httpx
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================================
# 0. НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================================
# 1. КОНФИГУРАЦИЯ
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
AGNES_API_URL = os.environ.get("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")
AI_MODEL = "agnes-2.0-flash"

os.environ["BU_CDP_URL"] = "http://localhost:9222"

# ============================================================
# 2. УПРАВЛЕНИЕ БРАУЗЕРОМ
# ============================================================

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
        logger.info("Браузер уже запущен")
        return True
    logger.info("Запускаем браузер...")
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
            logger.info(f"Браузер запущен! (через {i+1} сек)")
            return True
        logger.info(f"Ожидание... {i+1}/30")
    logger.error("Не удалось запустить браузер")
    return False

# ============================================================
# 3. РАБОТА С CLI BROWSER-HARNESS
# ============================================================

async def run_harness(code: str) -> tuple[str, str]:
    env = os.environ.copy()
    env["BU_CDP_URL"] = "http://localhost:9222"
    try:
        process = await asyncio.create_subprocess_exec(
            "browser-harness",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        stdout, stderr = await process.communicate(code.encode())
        return stdout.decode(), stderr.decode()
    except FileNotFoundError:
        return "", "browser-harness не найден. Установите: pip install browser-harness"
    except Exception as e:
        return "", f"Ошибка выполнения: {str(e)}"

# ============================================================
# 4. ХРАНИЛИЩЕ НАВЫКОВ
# ============================================================

SKILLS_DIR = "/app/agent-workspace/domain-skills"
os.makedirs(SKILLS_DIR, exist_ok=True)

def save_skill(domain: str, code: str, description: str = ""):
    domain_dir = os.path.join(SKILLS_DIR, domain)
    os.makedirs(domain_dir, exist_ok=True)
    skill_file = os.path.join(domain_dir, f"{domain}_skill.py")
    with open(skill_file, "w") as f:
        f.write(f'"""\n{description}\n"""\n\n{code}')
    return skill_file

def list_skills() -> list[str]:
    skills = []
    for domain in os.listdir(SKILLS_DIR):
        domain_path = os.path.join(SKILLS_DIR, domain)
        if os.path.isdir(domain_path):
            for f in os.listdir(domain_path):
                if f.endswith(".py"):
                    skills.append(f"{domain}/{f[:-3]}")
    return skills

# ============================================================
# 5. СИСТЕМНЫЙ ПРОМПТ (исправлен)
# ============================================================

SYSTEM_PROMPT = """
Ты — ИИ-агент, который управляет браузером через browser-harness.

Доступные хелперы (не требуют импорта):
- new_tab(url) - открыть новую вкладку
- wait_for_load() - дождаться загрузки
- page_info() - получить информацию о странице
- capture_screenshot(max_dim=1800) - сделать скриншот
- click_at_xy(x, y) - кликнуть по координатам
- type_text(text) - ввести текст
- press_key(key) - нажать клавишу
- scroll(x, y) - прокрутить страницу
- js(script) - выполнить JavaScript
- goto_url(url) - перейти по URL
- cdp(method, params) - отправить CDP-команду

Правила работы:
1. Если запрос простой — отвечай напрямую красивым текстом.
2. Если нужен браузер — пиши Python-код с хелперами.
3. Если функция не сработала — проанализируй ошибку и исправь код.
4. Успешные решения сохраняй как навыки для повторного использования.
5. ВСЕГДА возвращай результат через print(json.dumps(...)).
6. Добавляй try/except с выводом ошибок.
7. Используй time.sleep() для ожидания динамической загрузки.

ФОРМАТ ВЫВОДА (обязательно):
Возвращай данные в виде понятной структуры JSON с понятными ключами.
Используй понятные названия ключей на русском или английском.
Добавляй эмодзи в source для красоты (например, "🍎 Apple", "📱 MediaMarkt").
Всегда добавляй URL, если он есть.
Для цен указывай валюту.

Для скриншотов:
1. Используй capture_screenshot() и возвращай результат как JSON
2. В JSON добавь поля:
   - "action": "screenshot_taken"
   - "screenshot": "<base64-кодированное изображение>"
   - "note": "Описание"
   - "source": "Название сайта с эмодзи"

Пример кода для скриншота:
import json
import base64
try:
    new_tab("https://example.com")
    wait_for_load()
    img = capture_screenshot()
    print(json.dumps({{
        "action": "screenshot_taken",
        "source": "🌐 Example",
        "screenshot": base64.b64encode(img).decode(),
        "note": "Скриншот главной страницы"
    }}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))

ВАЖНО:
- Не используй слова "пример", "ориентировочно", "около" без необходимости
- Если точная цена неизвестна — напиши "цена не найдена"
- Для скриншотов всегда возвращай base64
- Ты можешь писать код прямо в ответе, обёрнутый в ```python ... ```.
"""

# ============================================================
# 6. LLM-АГЕНТ
# ============================================================

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
        logger.error(f"LLM ошибка: {e}")
        return f"Ошибка LLM: {str(e)[:200]}"

# ============================================================
# 7. ИСПОЛНИТЕЛЬ КОДА
# ============================================================

async def execute_agent_code(code: str, update: Update = None) -> tuple[str, bool]:
    try:
        code_match = re.search(r'```python\n(.*?)\n```', code, re.DOTALL)
        if code_match:
            code = code_match.group(1)
        dangerous = ['os.system', 'subprocess', '__import__', 'eval(', 'exec(']
        for d in dangerous:
            if d in code:
                return f"Обнаружена опасная операция: {d}", False
        if not any(h in code for h in ['new_tab', 'page_info', 'capture_screenshot', 'click_at_xy', 'js', 'cdp', 'goto_url']):
            return code, True
        stdout, stderr = await run_harness(code)
        if stderr:
            logger.warning(f"STDERR: {stderr[:200]}")
            return f"Ошибка: {stderr[:500]}", False
        if stdout:
            try:
                data = json.loads(stdout.strip())
                if update and isinstance(data, dict):
                    if data.get('action') == 'screenshot_taken':
                        screenshot_b64 = data.get('screenshot')
                        if screenshot_b64:
                            try:
                                img_bytes = base64.b64decode(screenshot_b64)
                                caption = f"📸 {data.get('source', 'Скриншот')}"
                                if data.get('note'):
                                    caption += f"\n\n{data.get('note')}"
                                await update.message.reply_photo(
                                    photo=img_bytes,
                                    caption=caption[:1024]
                                )
                                del data['screenshot']
                                return json.dumps(data, indent=2, ensure_ascii=False), True
                            except Exception as e:
                                logger.error(f"Ошибка отправки скриншота: {e}")
                                return f"Скриншот сделан, но не удалось отправить: {str(e)}", False
                return json.dumps(data, indent=2, ensure_ascii=False), True
            except:
                return stdout[:4000], True
        return "Выполнено успешно", True
    except Exception as e:
        logger.error(f"Ошибка выполнения: {e}")
        return f"Ошибка выполнения: {str(e)[:500]}", False

# ============================================================
# 8. КОМАНДЫ БОТА
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Агент с browser-harness**\n\n"
        "Я умею управлять браузером по твоим командам.\n"
        "Просто напиши, что нужно сделать.\n\n"
        "📋 Команды:\n"
        "/ask <запрос> - задать задачу\n"
        "/skills - список сохранённых навыков\n"
        "/status - статус системы\n"
        "/debug - диагностика браузера"
    )

async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🤖 **ИИ-агент с browser-harness**\n\n"
            "Просто опиши задачу, я решу, как её выполнить:\n"
            "• 'Покажи заголовок example.com'\n"
            "• 'Сделай скриншот github.com'\n"
            "• 'Найди контакты на сайте'\n"
            "• 'Кликни на кнопку входа'\n\n"
            "Пример: /ask какие цены на iPhone в Германии"
        )
        return
    user_query = " ".join(context.args)
    status_msg = await update.message.reply_text(f"🤔 Думаю над задачей: *{user_query[:50]}...*")
    try:
        skills = list_skills()
        context_text = f"\n\nДоступные навыки: {', '.join(skills)}" if skills else "\n\nНавыков пока нет."
        enhanced_query = f"""{user_query}

ВАЖНЫЕ ТРЕБОВАНИЯ К ФОРМАТУ ВЫВОДА:
1. ВСЕГДА выводи результат через print(json.dumps(...))
2. Используй понятные названия ключей на русском или английском
3. Добавляй эмодзи в поле source
4. Всегда добавляй URL, если он есть
5. Для скриншотов обязательно добавь поле "screenshot" с base64
6. Для скриншотов добавь поле "action": "screenshot_taken"

Пример правильного кода для скриншота:
import json
import base64
try:
    new_tab("https://example.com")
    wait_for_load()
    img = capture_screenshot()
    print(json.dumps({{
        "action": "screenshot_taken",
        "source": "🌐 Example",
        "screenshot": base64.b64encode(img).decode(),
        "note": "Скриншот главной страницы"
    }}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + context_text},
            {"role": "user", "content": enhanced_query}
        ]
        response = await ask_agnes(messages)
        logger.info(f"LLM ответ получен, длина: {len(response)}")
        if "```python" in response:
            await status_msg.edit_text("⚙️ Выполняю код...")
            result, success = await execute_agent_code(response, update)
            if success:
                await status_msg.edit_text("✅ Готово!")
                code_match = re.search(r'```python\n(.*?)\n```', response, re.DOTALL)
                if code_match and len(code_match.group(1)) > 50 and 'error' not in result.lower():
                    skill_code = code_match.group(1)
                    domain = "custom"
                    domains = {
                        'github': 'github', 'google': 'google',
                        'linkedin': 'linkedin', 'apple': 'apple',
                        'amazon': 'amazon', 'ebay': 'ebay', 'idealo': 'idealo'
                    }
                    for key, val in domains.items():
                        if key in user_query.lower():
                            domain = val
                            break
                    save_skill(domain, skill_code, user_query)
                    await update.message.reply_text(f"💾 Навык сохранён для домена '{domain}'")
                try:
                    data = json.loads(result)
                    if isinstance(data, dict) and data.get('action') == 'screenshot_taken':
                        if len(result) > 4000:
                            for i in range(0, len(result), 4000):
                                await update.message.reply_text(f"**Результат:**\n{result[i:i+4000]}")
                        else:
                            await update.message.reply_text(f"**Результат:**\n{result}")
                    else:
                        if len(result) > 4000:
                            for i in range(0, len(result), 4000):
                                await update.message.reply_text(f"**Результат:**\n{result[i:i+4000]}")
                        else:
                            await update.message.reply_text(f"**Результат:**\n{result}")
                except:
                    if len(result) > 4000:
                        for i in range(0, len(result), 4000):
                            await update.message.reply_text(f"**Результат:**\n{result[i:i+4000]}")
                    else:
                        await update.message.reply_text(f"**Результат:**\n{result}")
            else:
                await status_msg.edit_text("🔄 Исправляю ошибку...")
                error_messages = messages + [
                    {"role": "assistant", "content": response},
                    {"role": "user", "content": f"Код выдал ошибку. Исправь и предложи новый код.\nОшибка: {result}"}
                ]
                fixed_response = await ask_agnes(error_messages)
                if "```python" in fixed_response:
                    result2, success2 = await execute_agent_code(fixed_response, update)
                    if success2:
                        await status_msg.edit_text("✅ Исправлено!")
                        await update.message.reply_text(f"**Результат:**\n{result2[:4000]}")
                    else:
                        await update.message.reply_text(f"❌ Не удалось исправить:\n{result2}")
                else:
                    await update.message.reply_text(f"❌ Агент не смог исправить ошибку:\n{result}")
        else:
            await status_msg.edit_text("💬 Ответ:")
            if len(response) > 4000:
                for i in range(0, len(response), 4000):
                    await update.message.reply_text(response[i:i+4000])
            else:
                await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Ошибка в /ask: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def skills_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    skills = list_skills()
    if skills:
        msg = "💾 **Сохранённые навыки:**\n\n"
        for s in skills:
            msg += f"• `{s}`\n"
        await update.message.reply_text(msg, parse_mode='Markdown')
    else:
        await update.message.reply_text("💾 Нет сохранённых навыков.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    browser_ok = check_browser()
    status = "✅ работает" if browser_ok else "❌ не отвечает"
    try:
        process = await asyncio.create_subprocess_exec(
            "browser-harness", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        version = stdout.decode().strip() if stdout else "неизвестно"
        cli_status = f"✅ {version}"
    except:
        cli_status = "❌ не найден"
    llm_status = "✅ подключена" if AGNES_API_KEY else "❌ не задан ключ"
    skills_count = len(list_skills())
    await update.message.reply_text(
        f"**📊 Статус системы:**\n\n"
        f"🖥️ **Браузер:** {status}\n"
        f"🔧 **CLI browser-harness:** {cli_status}\n"
        f"🧠 **Agnes AI:** {llm_status}\n"
        f"💾 **Навыков:** {skills_count}"
    )

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("🔍 Запускаю диагностику...")
    code1 = '''
import json
try:
    new_tab("https://httpbin.org/html")
    wait_for_load()
    info = page_info()
    print(json.dumps({"test": "navigation", "title": info.get("title"), "status": "ok"}))
except Exception as e:
    print(json.dumps({"test": "navigation", "error": str(e)}))
'''
    stdout1, stderr1 = await run_harness(code1)
    code2 = '''
import json
try:
    new_tab("about:blank")
    result = js("return 'Hello from JS'")
    print(json.dumps({"test": "javascript", "result": result, "status": "ok"}))
except Exception as e:
    print(json.dumps({"test": "javascript", "error": str(e)}))
'''
    stdout2, stderr2 = await run_harness(code2)
    code3 = '''
import json
try:
    new_tab("https://httpbin.org/image/png")
    wait_for_load()
    img = capture_screenshot()
    print(json.dumps({"test": "screenshot", "bytes": len(img), "status": "ok"}))
except Exception as e:
    print(json.dumps({"test": "screenshot", "error": str(e)}))
'''
    stdout3, stderr3 = await run_harness(code3)
    code4 = '''
import json
import time
results = {}
try:
    new_tab("https://www.idealo.de/preisvergleich/")
    wait_for_load()
    time.sleep(2)
    search_check = js("""
        var input = document.querySelector('input[name="q"]');
        return input ? 'found' : 'not found';
    """)
    results["search_input"] = search_check
    if search_check == "found":
        js("""
            var input = document.querySelector('input[name="q"]');
            if (input) {
                input.value = 'iPhone 16';
                input.closest('form').submit();
            }
        """)
        time.sleep(3)
        prices = js("""
            var items = document.querySelectorAll('.product-price-value, .product-price, .price');
            var result = [];
            for (var i = 0; i < Math.min(items.length, 5); i++) {
                result.push(items[i].textContent.trim());
            }
            return result;
        """)
        results["prices"] = prices
        results["count"] = len(prices)
    else:
        results["error"] = "Поле поиска не найдено"
    results["url"] = page_info().get("url")
    if not results.get("prices") and not results.get("error"):
        screenshot = capture_screenshot()
        results["screenshot_size"] = len(screenshot)
except Exception as e:
    import traceback
    results["error"] = str(e)
    results["traceback"] = traceback.format_exc()[-200:]
print(json.dumps(results))
'''
    stdout4, stderr4 = await run_harness(code4)
    msg = "🔍 **Результаты диагностики:**\n\n"
    try:
        data1 = json.loads(stdout1) if stdout1 else {'error': 'пустой ответ'}
        msg += f"1️⃣ **Навигация:** "
        if 'error' in data1:
            msg += f"❌ {data1['error']}\n"
        else:
            msg += f"✅ {data1.get('title', 'ok')}\n"
    except:
        msg += f"1️⃣ **Навигация:** ⚠️ {stdout1[:50]}\n"
    try:
        data2 = json.loads(stdout2) if stdout2 else {'error': 'пустой ответ'}
        msg += f"2️⃣ **JavaScript:** "
        if 'error' in data2:
            msg += f"❌ {data2['error']}\n"
        else:
            msg += f"✅ {data2.get('result', 'ok')}\n"
    except:
        msg += f"2️⃣ **JavaScript:** ⚠️ {stdout2[:50]}\n"
    try:
        data3 = json.loads(stdout3) if stdout3 else {'error': 'пустой ответ'}
        msg += f"3️⃣ **Скриншот:** "
        if 'error' in data3:
            msg += f"❌ {data3['error']}\n"
        else:
            msg += f"✅ {data3.get('bytes', 0)} байт\n"
    except:
        msg += f"3️⃣ **Скриншот:** ⚠️ {stdout3[:50]}\n"
    msg += "\n4️⃣ **Поиск на Idealo:**\n"
    try:
        data4 = json.loads(stdout4) if stdout4 else {'error': 'пустой ответ'}
        if 'error' in data4:
            msg += f"   ❌ Ошибка: {data4['error']}\n"
        else:
            msg += f"   🔗 URL: {data4.get('url', 'неизвестно')}\n"
            msg += f"   🔍 Поле поиска: {data4.get('search_input', 'не найдено')}\n"
            if data4.get('prices'):
                msg += f"   💰 Цены: {', '.join(data4['prices'][:3])}\n"
                msg += f"   📊 Всего: {data4.get('count', 0)}\n"
            else:
                msg += "   ⚠️ Цены не найдены\n"
            if data4.get('screenshot_size'):
                msg += f"   📸 Скриншот сделан ({data4['screenshot_size']} байт)\n"
        if 'traceback' in data4:
            msg += f"   📋 Traceback: {data4['traceback']}\n"
    except Exception as e:
        msg += f"   ⚠️ Ошибка парсинга: {str(e)[:100]}\n"
        msg += f"   📄 stdout: {stdout4[:200]}\n"
    if stderr4:
        msg += f"\n⚠️ **STDERR:** {stderr4[:200]}"
    await status_msg.edit_text(msg[:4000])

# ============================================================
# 9. ЗАПУСК
# ============================================================

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
    logger.info("🚀 Запуск бота...")
    if not ensure_browser():
        logger.warning("⚠️ Браузер не запустился")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("skills", skills_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("debug", debug_command))
    logger.info("📋 Команды: /ask, /skills, /status, /debug")
    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()