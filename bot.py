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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
AGNES_API_URL = os.environ.get("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")
AI_MODEL = "agnes-2.0-flash"

os.environ["BU_CDP_URL"] = "http://localhost:9222"

# ============================================================
# 1. БРАУЗЕР
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
# 2. ЗАПУСК BROWSER-HARNESS
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
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(code.encode()),
                timeout=60.0
            )
            return stdout.decode(), stderr.decode()
        except asyncio.TimeoutError:
            process.kill()
            return "", "Таймаут выполнения browser-harness (60 сек)"
    except FileNotFoundError:
        return "", "browser-harness не найден"
    except Exception as e:
        return "", f"Ошибка выполнения: {str(e)}"

# ============================================================
# 3. НАВЫКИ (агент сам их создаёт)
# ============================================================

SKILLS_DIR = "/app/agent-workspace/domain-skills"
os.makedirs(SKILLS_DIR, exist_ok=True)

def save_skill(domain: str, code: str, description: str = ""):
    """Сохраняет навык — агент сам решает, когда это делать"""
    domain_dir = os.path.join(SKILLS_DIR, domain)
    os.makedirs(domain_dir, exist_ok=True)
    skill_file = os.path.join(domain_dir, f"{domain}_skill.py")
    with open(skill_file, "w") as f:
        f.write(f'"""\n{description}\n"""\n\n{code}')
    logger.info(f"💾 Навык сохранён: {domain}")
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

def get_skill_content(domain: str) -> str | None:
    skill_file = os.path.join(SKILLS_DIR, domain, f"{domain}_skill.py")
    if os.path.exists(skill_file):
        with open(skill_file, "r") as f:
            return f.read()
    return None

def load_all_skills_as_context() -> str:
    """Загружает все навыки как контекст для агента"""
    skills = list_skills()
    if not skills:
        return ""
    context = "\n\nДОСТУПНЫЕ НАВЫКИ (используй их как примеры):\n"
    for skill in skills:
        domain = skill.split('/')[0]
        content = get_skill_content(domain)
        if content:
            context += f"\n=== {skill} ===\n{content[:500]}...\n"
    return context

# ============================================================
# 4. ХЕЛПЕРЫ ДЛЯ САМОИСЦЕЛЕНИЯ
# ============================================================

HELPERS_PATH = "/app/agent-workspace/helpers.py"
os.makedirs(os.path.dirname(HELPERS_PATH), exist_ok=True)

def ensure_helpers():
    """Создаёт helpers.py если его нет — агент может его дополнять"""
    if not os.path.exists(HELPERS_PATH):
        with open(HELPERS_PATH, "w") as f:
            f.write('"""Агент может дописывать сюда новые хелперы"""\n\n')
    return HELPERS_PATH

def append_helper(code: str):
    """Агент может дописать новый хелпер в helpers.py"""
    with open(HELPERS_PATH, "a") as f:
        f.write(f"\n# Добавлено агентом\n{code}\n")
    logger.info("🧠 Хелпер дописан агентом")

# ============================================================
# 5. СИСТЕМНЫЙ ПРОМПТ (ПО ДОКУМЕНТАЦИИ)
# ============================================================

SYSTEM_PROMPT = """
Ты — ИИ-агент, управляющий браузером через browser-harness.

ГЛАВНЫЕ ПРИНЦИПЫ (из SKILL.md):

1. Скриншоты — ПЕРВЫЙ шаг. Всегда делай capture_screenshot(), чтобы понять страницу.
2. Клики — ТОЛЬКО по координатам. Скриншот → пиксели → click_at_xy(x, y) → скриншот для проверки. НИКАКИХ селекторов!
3. Навигация: ПЕРВАЯ — new_tab(url). Дальше — goto_url(url). После — wait_for_load().
4. Ввод текста: type_text(text) → press_key("Enter").
5. Если чего-то не хватает — допиши helpers.py сам и продолжай. Ты можешь создавать новые хелперы.

ХЕЛПЕРЫ (НЕ требуют импорта):
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

КОГДА использовать js():
- Только для ЧТЕНИЯ данных из DOM (текст, список товаров, атрибуты)
- НЕ для кликов, НЕ для навигации, НЕ для ввода

Для скриншотов ВСЕГДА используй CDP (это надёжнее в headless):
result = cdp("Page.captureScreenshot", {"format": "png", "quality": 80})
screenshot = result.get("data")

Для кликов (главное правило):
1. capture_screenshot() — увидеть страницу
2. click_at_xy(x, y) — клик по координатам (определил по скриншоту)
3. capture_screenshot() — проверить результат

ФОРМАТ ВЫВОДА:
Для скриншотов:
{
  "action": "screenshot_taken",
  "screenshot": "base64-строка",
  "source": "Название с эмодзи",
  "note": "Описание"
}

Для данных:
{
  "source": "Название",
  "data": {...},
  "url": "...",
  "note": "..."
}

Для ошибок:
{
  "error": "Описание ошибки"
}

КОГДА НЕ НУЖЕН БРАУЗЕР:
- Простые вопросы (погода, курс, факты, перевод) — отвечай текстом БЕЗ кода
- Если задача не требует браузера — не открывай его

САМОИСЦЕЛЕНИЕ:
- Если тебе не хватает хелпера — напиши его сам и продолжай
- Успешные решения сохраняй как навыки в /app/agent-workspace/domain-skills/<домен>/
- Используй сохранённые навыки как примеры

ВАЖНО:
- Клики — ТОЛЬКО по координатам, НЕ через селекторы
- ПЕРВАЯ навигация — ТОЛЬКО new_tab()
- После навигации ВСЕГДА wait_for_load()
- Скриншот — ПЕРВЫЙ шаг в любой задаче с браузером
- Для скриншотов — CDP
- ВСЕГДА оборачивай код в ```python ... ```
"""

# ============================================================
# 6. LLM АГЕНТ
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
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(AGNES_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            return "Неожиданный формат ответа"
    except httpx.TimeoutException:
        logger.error("Таймаут при запросе к Agnes AI")
        return "Ошибка: Agnes AI не отвечает (таймаут 45 сек)"
    except Exception as e:
        logger.error(f"LLM ошибка: {e}")
        return f"Ошибка LLM: {str(e)[:200]}"

# ============================================================
# 7. ИСПОЛНИТЕЛЬ КОДА С САМОИСЦЕЛЕНИЕМ
# ============================================================

async def execute_agent_code(code: str, update: Update = None) -> tuple[str, bool]:
    try:
        # Извлекаем код из markdown
        code_match = re.search(r'```python\n(.*?)\n```', code, re.DOTALL)
        if code_match:
            code = code_match.group(1)
        
        # Проверка на опасные операции
        dangerous = ['os.system', 'subprocess', '__import__', 'eval(', 'exec(']
        for d in dangerous:
            if d in code:
                return f"Обнаружена опасная операция: {d}", False
        
        # Если это создание хелпера — сохраняем
        if "helpers.py" in code or "def " in code and "helper" in code.lower():
            append_helper(code)
            return "🧠 Хелпер сохранён и будет доступен в следующих задачах", True
        
        # Если это навык — сохраняем отдельно
        if "domain-skills" in code:
            match = re.search(r'domain-skills/([^/]+)/', code)
            if match:
                domain = match.group(1)
                save_skill(domain, code, "Создано агентом")
        
        # Проверяем, есть ли хелперы
        if not any(h in code for h in ['new_tab', 'page_info', 'capture_screenshot', 'click_at_xy', 'js', 'cdp', 'goto_url']):
            return code, True
        
        # Выполняем код через browser-harness
        stdout, stderr = await run_harness(code)
        if stderr:
            logger.warning(f"STDERR: {stderr[:200]}")
            return f"Ошибка: {stderr[:500]}", False
        
        if stdout:
            try:
                data = json.loads(stdout.strip())
                
                # Отправка скриншота
                if update and isinstance(data, dict):
                    if data.get('action') == 'screenshot_taken':
                        screenshot_b64 = data.get('screenshot')
                        if screenshot_b64:
                            try:
                                if isinstance(screenshot_b64, bytes):
                                    screenshot_b64 = screenshot_b64.decode('utf-8')
                                if ',' in screenshot_b64:
                                    screenshot_b64 = screenshot_b64.split(',', 1)[1]
                                screenshot_b64 = screenshot_b64.strip()
                                missing_padding = len(screenshot_b64) % 4
                                if missing_padding:
                                    screenshot_b64 += '=' * (4 - missing_padding)
                                img_bytes = base64.b64decode(screenshot_b64)
                                if len(img_bytes) > 10 * 1024 * 1024:
                                    return "Скриншот слишком большой (>10MB)", False
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
        "Я управляю браузером по твоим командам.\n"
        "Работаю по принципам SKILL.md:\n"
        "• 📸 Скриншоты — первый шаг\n"
        "• 🖱️ Клики — только по координатам\n"
        "• 🧠 Сам учусь и создаю навыки\n\n"
        "📋 Команды:\n"
        "/ask <запрос> - задать задачу\n"
        "/skills - список навыков агента\n"
        "/status - статус системы\n"
        "/debug - диагностика"
    )

async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Просто опиши задачу:\n"
            "• 'Сделай скриншот google.com'\n"
            "• 'Найди кнопку входа на github.com'\n"
            "• 'Покажи цены на iPhone на apple.de'\n\n"
            "Пример: /ask сделай скриншот google.com"
        )
        return
    
    user_query = " ".join(context.args)
    status_msg = await update.message.reply_text(f"🤔 Думаю над задачей...")
    
    try:
        # Загружаем навыки как контекст
        skills_context = load_all_skills_as_context()
        
        enhanced_query = f"""{user_query}

{skills_context}

Если нужен браузер — напиши код в ```python ... ```.
Если задача простая (погода, факты) — ответь текстом.
Для кликов используй ТОЛЬКО координаты (скриншот → click_at_xy).
ПЕРВАЯ навигация — new_tab(), НЕ goto_url().
"""
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": enhanced_query}
        ]
        
        response = await ask_agnes(messages)
        logger.info(f"Ответ получен, длина: {len(response)}")
        
        if response.startswith("Ошибка"):
            await status_msg.edit_text(f"❌ {response}")
            return
        
        # Проверяем, есть ли код
        code_to_execute = None
        
        if "```python" in response:
            code_match = re.search(r'```python\n(.*?)\n```', response, re.DOTALL)
            if code_match:
                code_to_execute = code_match.group(1)
        elif any(h in response for h in ['new_tab', 'cdp', 'click_at_xy', 'capture_screenshot']):
            code_to_execute = response.strip()
            logger.info("Код найден без markdown — fallback")
        
        if code_to_execute:
            await status_msg.edit_text("⚙️ Выполняю код...")
            result, success = await execute_agent_code(code_to_execute, update)
            
            if success:
                await status_msg.edit_text("✅ Готово!")
                
                # Сохраняем как навык, если это успешный код с браузером
                if len(code_to_execute) > 100 and 'error' not in result.lower():
                    domain = "custom"
                    domains = ['google', 'github', 'apple', 'amazon', 'ebay', 'idealo', 'linkedin']
                    for d in domains:
                        if d in user_query.lower():
                            domain = d
                            break
                    save_skill(domain, code_to_execute, user_query)
                    await update.message.reply_text(f"💾 Агент сохранил навык для '{domain}'")
                
                if len(result) > 4000:
                    for i in range(0, len(result), 4000):
                        await update.message.reply_text(f"**Результат:**\n{result[i:i+4000]}")
                else:
                    await update.message.reply_text(f"**Результат:**\n{result}")
            else:
                await status_msg.edit_text("🔄 Исправляю ошибку...")
                
                # Самоисцеление — даём агенту шанс исправиться
                error_messages = messages + [
                    {"role": "assistant", "content": response},
                    {"role": "user", "content": f"Код выдал ошибку. Исправь.\nОшибка: {result}"}
                ]
                fixed_response = await ask_agnes(error_messages)
                
                if "```python" in fixed_response:
                    code_match = re.search(r'```python\n(.*?)\n```', fixed_response, re.DOTALL)
                    fixed_code = code_match.group(1) if code_match else fixed_response.strip()
                    result2, success2 = await execute_agent_code(fixed_code, update)
                    if success2:
                        await status_msg.edit_text("✅ Исправлено!")
                        await update.message.reply_text(f"**Результат:**\n{result2[:4000]}")
                    else:
                        await update.message.reply_text(f"❌ Не удалось исправить:\n{result2}")
                else:
                    await update.message.reply_text(f"❌ Агент не смог исправить:\n{result}")
        else:
            await status_msg.edit_text("💬 Ответ:")
            if len(response) > 4000:
                for i in range(0, len(response), 4000):
                    await update.message.reply_text(response[i:i+4000])
            else:
                await update.message.reply_text(response)
                
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def skills_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    skills = list_skills()
    if skills:
        msg = "🧠 **Навыки агента:**\n\n"
        for s in skills:
            msg += f"• `{s}`\n"
        await update.message.reply_text(msg, parse_mode='Markdown')
    else:
        await update.message.reply_text("🧠 Агент ещё не создал навыков. Дайте ему задачу!")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    browser_ok = check_browser()
    status = "✅ работает" if browser_ok else "❌ не отвечает"
    try:
        process = await asyncio.create_subprocess_exec(
            "browser-harness", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=5.0)
        version = stdout.decode().strip() if stdout else "неизвестно"
        cli_status = f"✅ {version}"
    except:
        cli_status = "❌ не найден"
    llm_status = "✅ подключена" if AGNES_API_KEY else "❌ не задан ключ"
    skills_count = len(list_skills())
    await update.message.reply_text(
        f"**📊 Статус:**\n\n"
        f"🖥️ Браузер: {status}\n"
        f"🔧 browser-harness: {cli_status}\n"
        f"🧠 Agnes AI: {llm_status}\n"
        f"💾 Навыков: {skills_count}"
    )

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("🔍 Диагностика...")
    
    code = '''
import json
try:
    new_tab("https://httpbin.org/html")
    wait_for_load()
    info = page_info()
    print(json.dumps({"navigation": "ok", "title": info.get("title")}))
except Exception as e:
    print(json.dumps({"error": str(e)}))
'''
    stdout, stderr = await run_harness(code)
    
    msg = "🔍 **Результаты:**\n\n"
    try:
        data = json.loads(stdout) if stdout else {'error': 'пусто'}
        if 'error' in data:
            msg += f"❌ {data['error']}\n"
        else:
            msg += f"✅ Навигация: {data.get('title', 'ok')}\n"
    except:
        msg += f"⚠️ {stdout[:100]}\n"
    
    if stderr:
        msg += f"\n⚠️ Ошибки: {stderr[:200]}"
    
    await status_msg.edit_text(msg)

# ============================================================
# 9. ЗАПУСК
# ============================================================

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
    
    logger.info("🚀 Запуск бота...")
    ensure_helpers()
    
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