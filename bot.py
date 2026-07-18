import os
import subprocess
import asyncio
import json
import re
import time
import base64
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
AGNES_API_URL = os.environ.get("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")
AI_MODEL = "agnes-2.0-flash"

os.environ["BU_CDP_URL"] = "http://localhost:9222"

# ============================================================
# 1. УПРАВЛЕНИЕ БРАУЗЕРОМ
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
        print("✅ Браузер уже запущен")
        return True
    
    print("🔄 Запускаем браузер...")
    
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
            print(f"✅ Браузер запущен! (через {i+1} сек)")
            return True
        print(f"   Ожидание... {i+1}/30")
    
    print("❌ Не удалось запустить браузер")
    return False

# ============================================================
# 2. РАБОТА С CLI BROWSER-HARNESS
# ============================================================

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

# ============================================================
# 3. ХРАНИЛИЩЕ НАВЫКОВ
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
# 4. СИСТЕМНЫЙ ПРОМПТ
# ============================================================

SYSTEM_PROMPT = """
Ты — ИИ-агент, который управляет браузером через browser-harness.

**Доступные хелперы (не требуют импорта):**
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

**Правила работы:**
1. Если запрос простой — отвечай напрямую.
2. Если нужен браузер — пиши Python-код с хелперами.
3. Если функция не сработала — проанализируй ошибку и исправь код.
4. Успешные решения сохраняй как навыки для повторного использования.
5. Для кликов используй координаты (клик по картинке), а не селекторы.
6. ВСЕГДА возвращай результат через print().

**ВАЖНО:** Ты можешь писать код прямо в ответе, обёрнутый в ```python ... ```.
"""

# ============================================================
# 5. LLM-АГЕНТ
# ============================================================

async def ask_agnes(messages: list[dict]) -> str:
    if not AGNES_API_KEY:
        return "❌ Ошибка: AGNES_API_KEY не задан."

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
            return "⚠️ Неожиданный формат ответа"
    except Exception as e:
        return f"❌ Ошибка LLM: {str(e)[:200]}"

# ============================================================
# 6. ИСПОЛНИТЕЛЬ КОДА
# ============================================================

async def execute_agent_code(code: str) -> tuple[str, bool]:
    try:
        code_match = re.search(r'```python\n(.*?)\n```', code, re.DOTALL)
        if code_match:
            code = code_match.group(1)
        
        if not any(h in code for h in ['new_tab', 'page_info', 'capture_screenshot', 'click_at_xy', 'js', 'cdp']):
            return code, True
        
        stdout, stderr = await run_harness(code)
        if stderr:
            return f"❌ Ошибка: {stderr[:500]}", False
        
        if stdout:
            try:
                data = json.loads(stdout.strip())
                return json.dumps(data, indent=2, ensure_ascii=False), True
            except:
                return stdout[:4000], True
        return "✅ Выполнено успешно", True
    except Exception as e:
        return f"❌ Ошибка выполнения: {str(e)[:500]}", False

# ============================================================
# 7. КОМАНДЫ БОТА
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
        "/debug - диагностика"
    )

async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🤖 **ИИ-агент с browser-harness**\n\n"
            "Просто опиши задачу, я решу, как её выполнить:\n"
            "• 'Покажи заголовок example.com'\n"
            "• 'Сделай скриншот github.com'\n"
            "• 'Найди контакты на сайте'\n"
            "• 'Кликни на кнопку входа'"
        )
        return

    user_query = " ".join(context.args)
    status_msg = await update.message.reply_text(f"🤔 Думаю над задачей...")

    try:
        skills = list_skills()
        context_text = f"\n\nДоступные навыки: {', '.join(skills)}" if skills else "\n\nНавыков пока нет."

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + context_text},
            {"role": "user", "content": user_query}
        ]
        
        response = await ask_agnes(messages)
        
        if "```python" in response:
            await status_msg.edit_text("⚙️ Выполняю код...")
            
            result, success = await execute_agent_code(response)
            
            if success:
                await status_msg.edit_text("✅ Готово!")
                
                code_match = re.search(r'```python\n(.*?)\n```', response, re.DOTALL)
                if code_match and len(code_match.group(1)) > 50:
                    skill_code = code_match.group(1)
                    domain = "custom"
                    if "github" in user_query.lower():
                        domain = "github"
                    elif "google" in user_query.lower():
                        domain = "google"
                    elif "linkedin" in user_query.lower():
                        domain = "linkedin"
                    
                    save_skill(domain, skill_code, user_query)
                    await update.message.reply_text(f"💾 Навык сохранён для домена '{domain}'")
                
                await update.message.reply_text(f"**Результат:**\n{result[:4000]}")
            else:
                await status_msg.edit_text("🔄 Исправляю ошибку...")
                
                error_messages = messages + [
                    {"role": "assistant", "content": response},
                    {"role": "user", "content": f"Код выдал ошибку. Исправь её и предложи новый код.\nОшибка: {result}"}
                ]
                fixed_response = await ask_agnes(error_messages)
                
                if "```python" in fixed_response:
                    result2, success2 = await execute_agent_code(fixed_response)
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
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def skills_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    skills = list_skills()
    if skills:
        await update.message.reply_text(f"💾 **Сохранённые навыки:**\n\n" + "\n".join([f"• {s}" for s in skills]))
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
        f"**Браузер:** {status}\n"
        f"**CLI browser-harness:** {cli_status}\n"
        f"**Agnes AI:** {llm_status}\n"
        f"**Навыков:** {skills_count}"
    )

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = """
import json
results = {}
try:
    new_tab("about:blank")
    results['new_tab'] = '✅ работает'
except Exception as e:
    results['new_tab'] = f'❌ {str(e)[:30]}'
try:
    wait_for_load()
    results['wait_for_load'] = '✅ работает'
except Exception as e:
    results['wait_for_load'] = f'❌ {str(e)[:30]}'
try:
    info = page_info()
    results['page_info'] = f'✅ работает: {info.get("title", "no title")[:20]}'
except Exception as e:
    results['page_info'] = f'❌ {str(e)[:30]}'
try:
    data = capture_screenshot()
    results['capture_screenshot'] = f'✅ работает, размер: {len(data)} байт'
except Exception as e:
    results['capture_screenshot'] = f'❌ {str(e)[:30]}'
print(json.dumps(results))
"""
    stdout, stderr = await run_harness(code)
    msg = "🔍 **Диагностика:**\n\n"
    if stdout:
        try:
            data = json.loads(stdout.strip())
            for key, value in data.items():
                msg += f"• {key}: {value}\n"
        except:
            msg += stdout
    if stderr:
        msg += f"\nОшибки: {stderr[:200]}"
    await update.message.reply_text(msg[:4000])

# ============================================================
# 8. ЗАПУСК
# ============================================================

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
    
    if not ensure_browser():
        print("⚠️ Браузер не запустился")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("skills", skills_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("debug", debug_command))
    
    print("🚀 Агент запускается...")
    print("📋 Команды: /ask, /skills, /status, /debug")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()