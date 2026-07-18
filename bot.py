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
                timeout=30.0
            )
            return stdout.decode(), stderr.decode()
        except asyncio.TimeoutError:
            process.kill()
            return "", "Таймаут выполнения browser-harness (30 сек)"
    except FileNotFoundError:
        return "", "browser-harness не найден"
    except Exception as e:
        return "", f"Ошибка выполнения: {str(e)}"

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

SYSTEM_PROMPT = """
Ты — ИИ-агент, который управляет браузером через browser-harness.

ОСНОВНЫЕ ПРИНЦИПЫ (из документации):

1. Скриншоты — первый шаг: Всегда используй CDP-метод для скриншотов.
2. Клики по координатам: Скриншот -> прочитай пиксели -> click_at_xy(x, y). НЕ используй селекторы!
3. Навигация: Первая навигация — new_tab(url). После навигации — wait_for_load().
4. Ввод текста: type_text(text) + press_key("Enter").

ХЕЛПЕРЫ:
new_tab(url), goto_url(url), wait_for_load(), page_info(),
capture_screenshot(max_dim=800), click_at_xy(x, y), type_text(text),
press_key(key), scroll(x, y), js(script), cdp(method, params), ensure_real_tab()

ВАЖНО: Для скриншотов ВСЕГДА используй CDP-метод (надёжнее в headless-режиме):

ПРАВИЛЬНЫЙ КОД ДЛЯ СКРИНШОТА:
import json
try:
    new_tab("https://example.com")
    wait_for_load()
    result = cdp("Page.captureScreenshot", {"format": "png", "quality": 80})
    print(json.dumps({
        "action": "screenshot_taken",
        "source": "🌐 Example",
        "screenshot": result.get("data"),
        "note": "Скриншот главной страницы"
    }))
except Exception as e:
    print(json.dumps({"error": str(e)}))

ФОРМАТ ВЫВОДА:
Для скриншотов:
{
  "action": "screenshot_taken",
  "screenshot": "base64-строка",
  "source": "Название с эмодзи",
  "note": "Описание"
}

Для ошибок:
{
  "error": "Описание ошибки"
}

ВАЖНО:
- НЕ используй селекторы для кликов — только координаты
- ПЕРВАЯ навигация — ТОЛЬКО new_tab()
- После навигации ВСЕГДА wait_for_load()
- Для скриншотов используй cdp("Page.captureScreenshot", {"format": "png", "quality": 80})
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
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(AGNES_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            return "Неожиданный формат ответа"
    except httpx.TimeoutException:
        logger.error("Таймаут при запросе к Agnes AI")
        return "Ошибка: Agnes AI не отвечает (таймаут 30 сек)"
    except Exception as e:
        logger.error(f"LLM ошибка: {e}")
        return f"Ошибка LLM: {str(e)[:200]}"

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
            "• 'Сделай скриншот google.com'\n"
            "• 'Найди цены на iPhone'\n"
            "• 'Кликни на кнопку входа'\n\n"
            "Пример: /ask сделай скриншот google.com"
        )
        return
    
    user_query = " ".join(context.args)
    status_msg = await update.message.reply_text(f"🤔 Думаю над задачей: *{user_query[:50]}...*")
    
    try:
        skills = list_skills()
        context_text = f"\n\nДоступные навыки: {', '.join(skills)}" if skills else "\n\nНавыков пока нет."
        
        enhanced_query = f"""{user_query}

ВАЖНЫЕ ТРЕБОВАНИЯ:
1. ВСЕГДА выводи результат через print(json.dumps(...))
2. Для скриншотов используй CDP:
   result = cdp("Page.captureScreenshot", {{"format": "png", "quality": 80}})
   screenshot = result.get("data")
3. НЕ используй capture_screenshot() - она ненадёжна в headless-режиме
4. Для кликов используй координаты, НЕ селекторы
5. ПЕРВАЯ навигация — new_tab(), НЕ goto_url()
6. После навигации ВСЕГДА wait_for_load()

Пример правильного кода для скриншота:
import json
try:
    new_tab("https://google.com")
    wait_for_load()
    result = cdp("Page.captureScreenshot", {{"format": "png", "quality": 80}})
    print(json.dumps({{
        "action": "screenshot_taken",
        "source": "🔍 Google",
        "screenshot": result.get("data"),
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
        
        if response.startswith("Ошибка"):
            await status_msg.edit_text(f"❌ {response}")
            return
        
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
                
                if fixed_response.startswith("Ошибка"):
                    await update.message.reply_text(f"❌ {fixed_response}")
                    return
                
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
                
    except asyncio.TimeoutError:
        await status_msg.edit_text("❌ Таймаут выполнения запроса. Попробуйте позже.")
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
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=5.0)
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
    result = cdp("Page.captureScreenshot", {"format": "png", "quality": 80})
    img = result.get("data", "")
    print(json.dumps({"test": "screenshot", "bytes": len(img), "status": "ok"}))
except Exception as e:
    print(json.dumps({"test": "screenshot", "error": str(e)}))
'''
    stdout3, stderr3 = await run_harness(code3)
    
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
        msg += f"3️⃣ **Скриншот (CDP):** "
        if 'error' in data3:
            msg += f"❌ {data3['error']}\n"
        else:
            msg += f"✅ {data3.get('bytes', 0)} байт\n"
    except:
        msg += f"3️⃣ **Скриншот (CDP):** ⚠️ {stdout3[:50]}\n"
    
    if stderr1 or stderr2 or stderr3:
        msg += f"\n⚠️ **Ошибки:**"
        if stderr1:
            msg += f"\n• {stderr1[:100]}"
        if stderr2:
            msg += f"\n• {stderr2[:100]}"
        if stderr3:
            msg += f"\n• {stderr3[:100]}"
    
    await status_msg.edit_text(msg[:4000])

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