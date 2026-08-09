# bot.py
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
from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from promt import SYSTEM_PROMPT
from PIL import Image

# ============================================================
# DSPy + Agnes
# ============================================================
import dspy
from dspy.teleprompt import BootstrapFewShot

warnings.filterwarnings("ignore")

# ============================================================
# НАСТРОЙКА ОКРУЖЕНИЯ
# ============================================================

agent_workspace = "/app/browser-harness/agent-workspace"
sys.path.insert(0, agent_workspace)

helpers_file = os.path.join(agent_workspace, "agent_helpers.py")
os.makedirs(agent_workspace, exist_ok=True)
if not os.path.exists(helpers_file):
    with open(helpers_file, "w") as f:
        f.write('"""Agent-editable browser helpers."""\n')
os.chmod(agent_workspace, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
os.chmod(helpers_file, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)

os.environ["BH_DOMAIN_SKILLS"] = "1"
os.environ["BH_AGENT_WORKSPACE"] = "/app/browser-harness/agent-workspace"

LOGS_DIR = '/app/logs'
SCREENSHOTS_DIR = '/app/screenshots'
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'bot.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("telegram").setLevel(logging.CRITICAL)
logging.getLogger("telegram.ext").setLevel(logging.CRITICAL)
logging.getLogger("dspy").setLevel(logging.INFO)

logger = logging.getLogger(__name__)
logger.info(f"✅ agent_workspace: {agent_workspace}")
logger.info(f"✅ helpers_file: {helpers_file}")
logger.info(f"✅ screenshots_dir: {SCREENSHOTS_DIR}")

sys.path.insert(0, "browser-harness/src")

from browser_harness.helpers import (
    new_tab, goto_url, wait_for_load, page_info, capture_screenshot,
    click_at_xy, type_text, press_key, scroll, js, cdp, ensure_real_tab,
    wait_for_element, list_tabs, current_tab, close_tab, switch_tab,
    fill_input, upload_file, http_get, drain_events
)
from browser_harness.admin import ensure_daemon

# ============================================================
# КУКИ (WebSocket)
# ============================================================

try:
    from cookies import COOKIES
    import websockets
    import json
    
    async def set_cookies_async():
        try:
            import httpx
            resp = httpx.get("http://localhost:9222/json/list", timeout=5.0)
            pages = resp.json()
            if not pages:
                logger.error("❌ Нет активных вкладок")
                return False
            ws_url = pages[0]["webSocketDebuggerUrl"]
            logger.info("🔗 Подключаюсь к WebSocket...")
            async with websockets.connect(ws_url) as ws:
                await ws.send(json.dumps({"id": 1, "method": "Network.setCookies", "params": {"cookies": COOKIES}}))
                response = json.loads(await ws.recv())
                if "error" in response:
                    logger.error(f"❌ CDP ошибка: {response['error']}")
                    return False
                logger.info(f"🍪 Установлено {len(COOKIES)} кук")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    def set_cookies_global():
        try:
            loop = asyncio.get_running_loop()
            return asyncio.run_coroutine_threadsafe(set_cookies_async(), loop).result(timeout=10)
        except RuntimeError:
            return asyncio.run(set_cookies_async())
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False

except ImportError:
    logger.warning("⚠️ websockets не установлен")
    COOKIES = []
    def set_cookies_global():
        return False

# ============================================================
# НАСТРОЙКА РАЗМЕРА ОКНА (WebSocket)
# ============================================================

async def set_viewport_async():
    try:
        import httpx
        resp = httpx.get("http://localhost:9222/json/list", timeout=5.0)
        pages = resp.json()
        if not pages:
            logger.warning("⚠️ Нет активных вкладок для установки размера")
            return False
        ws_url = pages[0]["webSocketDebuggerUrl"]
        logger.info("🔗 Подключаюсь к WebSocket для установки размера...")
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({
                "id": 2,
                "method": "Emulation.setDeviceMetricsOverride",
                "params": {
                    "width": 1280,
                    "height": 720,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                    "screenWidth": 1280,
                    "screenHeight": 720,
                    "positionX": 0,
                    "positionY": 0
                }
            }))
            response = json.loads(await ws.recv())
            if "error" in response:
                logger.warning(f"⚠️ CDP ошибка: {response['error']}")
                return False
            logger.info("✅ Размер окна установлен: 1280x720")
            return True
    except Exception as e:
        logger.warning(f"⚠️ Не удалось установить размер окна: {e}")
        return False

def set_viewport_global():
    try:
        loop = asyncio.get_running_loop()
        return asyncio.run_coroutine_threadsafe(set_viewport_async(), loop).result(timeout=10)
    except RuntimeError:
        return asyncio.run(set_viewport_async())
    except Exception as e:
        logger.warning(f"⚠️ Не удалось установить размер окна: {e}")
        return False

# ============================================================
# НАСТРОЙКА
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

os.environ["BU_CDP_URL"] = "http://localhost:9222"
ensure_daemon()
logger.info("✅ Браузер готов")

set_cookies_global()
set_viewport_global()

# ============================================================
# AGNES LM ДЛЯ DSPy
# ============================================================

class AgnesLM(dspy.LM):
    def __init__(self, model="agnes-2.0-flash", api_key=None, **kwargs):
        self.model = model
        self.api_key = api_key or os.environ.get("AGNES_API_KEY")
        self.kwargs = kwargs
        self.history = []
        
        if not self.api_key:
            raise ValueError("AGNES_API_KEY не задан!")
    
    def __call__(self, prompt, **kwargs):
        messages = [{"role": "user", "content": prompt}]
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.3),
            "max_tokens": kwargs.get("max_tokens", 2000)
        }
        
        try:
            response = httpx.post(
                "https://apihub.agnes-ai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=45.0
            )
            response.raise_for_status()
            data = response.json()
            result = data["choices"][0]["message"]["content"]
            
            self.history.append({
                "prompt": prompt,
                "response": result,
                "kwargs": kwargs
            })
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка Agnes AI: {e}")
            return f"Ошибка: {str(e)}"
    
    def get_history(self):
        return self.history

# ============================================================
# ОПРЕДЕЛЕНИЕ СИГНАТУР DSPy
# ============================================================

class BrowserPlan(dspy.Signature):
    user_query = dspy.InputField(desc="Запрос пользователя")
    plan = dspy.OutputField(desc="Пошаговый план действий")
    code = dspy.OutputField(desc="Python код для выполнения")
    explanation = dspy.OutputField(desc="Объяснение решения")

class FixError(dspy.Signature):
    error = dspy.InputField(desc="Текст ошибки")
    broken_code = dspy.InputField(desc="Сломанный код")
    fixed_code = dspy.OutputField(desc="Исправленный код")
    explanation = dspy.OutputField(desc="Что было исправлено")

class ExtractSkill(dspy.Signature):
    user_query = dspy.InputField(desc="Запрос пользователя")
    code = dspy.InputField(desc="Рабочий код")
    skill_name = dspy.OutputField(desc="Название навыка (одно слово)")
    skill_description = dspy.OutputField(desc="Описание навыка")
    skill_code = dspy.OutputField(desc="Код навыка (функция)")

# ============================================================
# DSPy + AGNES АГЕНТ
# ============================================================

class BrowserAgent(dspy.Module):
    def __init__(self, lm=None):
        super().__init__()
        
        if lm is None:
            self.lm = AgnesLM()
            dspy.settings.configure(lm=self.lm)
        else:
            self.lm = lm
            dspy.settings.configure(lm=lm)
        
        self.planner = dspy.ChainOfThought(BrowserPlan)
        self.fixer = dspy.ChainOfThought(FixError)
        self.skill_extractor = dspy.ChainOfThought(ExtractSkill)
        
        self.skills = {}
        self._load_skills()
        
        logger.info("✅ DSPy + Agnes агент инициализирован")
    
    def _load_skills(self):
        skills_dir = os.path.join(agent_workspace, "domain-skills")
        if not os.path.exists(skills_dir):
            return
        
        for domain in os.listdir(skills_dir):
            domain_path = os.path.join(skills_dir, domain)
            if os.path.isdir(domain_path):
                for f in os.listdir(domain_path):
                    if f.endswith(".md"):
                        skill_path = os.path.join(domain_path, f)
                        try:
                            with open(skill_path, 'r', encoding='utf-8') as file:
                                content = file.read()
                                skill_name = f.replace(".md", "")
                                self.skills[skill_name] = {
                                    "name": skill_name,
                                    "domain": domain,
                                    "content": content,
                                    "path": skill_path
                                }
                        except Exception as e:
                            logger.warning(f"⚠️ Не удалось загрузить навык {f}: {e}")
        
        logger.info(f"📚 Загружено {len(self.skills)} навыков")
    
    def forward(self, user_query: str, max_retries: int = 3):
        logger.info(f"🤔 Планирую: {user_query}")
        plan_result = self.planner(user_query=user_query)
        
        plan = plan_result.plan
        code = plan_result.code
        explanation = plan_result.explanation
        
        logger.info(f"📝 План:\n{plan}")
        logger.info(f"💻 Код:\n{code}")
        
        output, success = self._execute_code(code)
        
        attempt = 0
        while not success and attempt < max_retries:
            logger.info(f"🔧 Исправляю ошибку (попытка {attempt + 1})")
            
            fix_result = self.fixer(
                error=output,
                broken_code=code
            )
            
            code = fix_result.fixed_code
            logger.info(f"🔄 Исправленный код:\n{code}")
            
            output, success = self._execute_code(code)
            attempt += 1
        
        skill_created = False
        if success and len(code) > 50:
            skill = self._extract_skill(user_query, code)
            if skill:
                self.skills[skill['name']] = skill
                self._save_skill(skill)
                skill_created = True
        
        return {
            "success": success,
            "plan": plan,
            "code": code,
            "output": output,
            "explanation": explanation,
            "retries": attempt,
            "skill_created": skill_created
        }
    
    def _execute_code(self, code: str):
        return execute_code(code)
    
    def _extract_skill(self, user_query: str, code: str):
        try:
            result = self.skill_extractor(
                user_query=user_query,
                code=code
            )
            
            return {
                "name": result.skill_name.lower().replace(" ", "_"),
                "description": result.skill_description,
                "code": result.skill_code,
                "domain": "auto"
            }
        except Exception as e:
            logger.warning(f"⚠️ Не удалось извлечь навык: {e}")
            return None
    
    def _save_skill(self, skill: dict):
        try:
            skills_dir = os.path.join(agent_workspace, "domain-skills", skill.get("domain", "auto"))
            os.makedirs(skills_dir, exist_ok=True)
            
            skill_path = os.path.join(skills_dir, f"{skill['name']}.md")
            
            content = f"# {skill['name']}\n\n**Описание:** {skill.get('description', 'Автоматически созданный навык')}\n\n**Код:**\n```python\n{skill['code']}\n```\n"
            
            with open(skill_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"✅ Навык сохранён: {skill_path}")
            
            push_to_github(content, f"{skill['name']}.md", skill.get("domain", "auto"))
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения навыка: {e}")
    
    def use_skill(self, skill_name: str) -> dict:
        if skill_name in self.skills:
            skill = self.skills[skill_name]
            
            if 'code' in skill:
                output, success = self._execute_code(skill['code'])
                return {
                    "success": success,
                    "skill": skill_name,
                    "output": output
                }
            elif 'path' in skill:
                try:
                    with open(skill['path'], 'r', encoding='utf-8') as f:
                        content = f.read()
                        code_match = re.search(r'```python\n(.*?)\n```', content, re.DOTALL)
                        if code_match:
                            code = code_match.group(1)
                            output, success = self._execute_code(code)
                            return {
                                "success": success,
                                "skill": skill_name,
                                "output": output
                            }
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"Ошибка загрузки навыка: {e}"
                    }
        
        return {
            "success": False,
            "error": f"Навык '{skill_name}' не найден"
        }

# ============================================================
# GITHUB
# ============================================================

def push_to_github(content, filename, host="x.com"):
    if not GITHUB_TOKEN:
        logger.warning("⚠️ GITHUB_TOKEN не задан, навык не будет отправлен в GitHub")
        return False

    repo = "carzyben94/Bugaga"
    branch = "main"
    file_path = f"browser-harness/agent-workspace/domain-skills/{host}/{filename}"
    url = f"https://api.github.com/repos/{repo}/contents/{file_path}"

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        resp = httpx.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            sha = resp.json().get("sha")
        else:
            sha = None
    except Exception:
        sha = None

    data = {
        "message": f"Добавлен/обновлён навык {filename} для {host}",
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch
    }
    if sha:
        data["sha"] = sha

    try:
        response = httpx.put(url, headers=headers, json=data, timeout=30)
        if response.status_code in [200, 201]:
            logger.info(f"✅ Навык отправлен в GitHub: {file_path}")
            return True
        else:
            logger.error(f"❌ Ошибка отправки в GitHub: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке в GitHub: {e}")
        return False

def push_helpers_to_github():
    if not GITHUB_TOKEN:
        logger.warning("⚠️ GITHUB_TOKEN не задан, helpers не будут отправлены")
        return False
    
    repo = "carzyben94/Bugaga"
    branch = "main"
    file_path = "browser-harness/agent-workspace/agent_helpers.py"
    url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        resp = httpx.get(url, headers=headers, timeout=10)
        sha = resp.json().get("sha", None) if resp.status_code == 200 else None
    except:
        sha = None
    
    helpers_path = os.path.join(agent_workspace, "agent_helpers.py")
    if not os.path.exists(helpers_path):
        logger.warning("⚠️ agent_helpers.py не найден")
        return False
    
    with open(helpers_path, "r", encoding='utf-8') as f:
        content = f.read()
    
    data = {
        "message": "Обновлён agent_helpers.py",
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch
    }
    if sha:
        data["sha"] = sha
    
    try:
        response = httpx.put(url, headers=headers, json=data, timeout=30)
        if response.status_code in [200, 201]:
            logger.info(f"✅ agent_helpers.py отправлен в GitHub")
            return True
        else:
            logger.error(f"❌ Ошибка отправки helpers: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке helpers: {e}")
        return False

# ============================================================
# ВЫПОЛНИТЕЛЬ КОДА
# ============================================================

def execute_code(code):
    logger.info(f"⚙️ ВЫПОЛНЕНИЕ КОДА:\n{code}")
    try:
        stdout_buffer = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = stdout_buffer
        
        def save_skill(host, name, content):
            skills_dir = os.path.join(agent_workspace, "domain-skills", host)
            os.makedirs(skills_dir, exist_ok=True)
            os.chmod(skills_dir, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
            
            skill_path = os.path.join(skills_dir, f"{name}.md")
            with open(skill_path, "w", encoding='utf-8') as f:
                f.write(content)
            os.chmod(skill_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)
            
            logger.info(f"✅ Навык сохранён локально: {skill_path}")
            
            push_to_github(content, f"{name}.md", host)
            
            return skill_path
        
        def add_helper(code):
            helpers_path = os.path.join(agent_workspace, "agent_helpers.py")
            
            if not os.path.exists(helpers_path):
                with open(helpers_path, "w") as f:
                    f.write('"""Agent-editable browser helpers."""\n')
            
            with open(helpers_path, "a", encoding='utf-8') as f:
                f.write(f"\n\n{code}\n")
            
            logger.info(f"✅ Helper добавлен в agent_helpers.py")
            push_helpers_to_github()
            return True
        
        def capture_screenshot_with_path(path=None, full=False, max_dim=None):
            if path is None:
                timestamp = int(time.time())
                filename = f"screenshot_{timestamp}.png"
                full_path = os.path.join(SCREENSHOTS_DIR, filename)
            else:
                filename = os.path.basename(path)
                full_path = os.path.join(SCREENSHOTS_DIR, filename)
            logger.info(f"📸 Сохраняю скриншот в: {full_path}")
            return capture_screenshot(path=full_path, full=False, max_dim=max_dim)
        
        globals_dict = {
            'new_tab': new_tab, 
            'goto_url': goto_url, 
            'wait_for_load': wait_for_load,
            'page_info': page_info, 
            'capture_screenshot': capture_screenshot_with_path,
            'click_at_xy': click_at_xy, 
            'type_text': type_text, 
            'press_key': press_key,
            'scroll': scroll,
            'scroll_at_xy': scroll,
            'js': js, 
            'cdp': cdp, 
            'ensure_real_tab': ensure_real_tab,
            'wait_for_element': wait_for_element, 
            'list_tabs': list_tabs,
            'current_tab': current_tab, 
            'close_tab': close_tab,
            'switch_tab': switch_tab,
            'fill_input': fill_input,
            'upload_file': upload_file,
            'http_get': http_get,
            'drain_events': drain_events,
            'set_cookies': set_cookies_global,
            'save_skill': save_skill,
            'add_helper': add_helper,
            'time': time,
            'json': json,
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
        return str(e), False

# ============================================================
# ИНИЦИАЛИЗАЦИЯ DSPy АГЕНТА
# ============================================================

agnes_lm = AgnesLM(
    model="agnes-2.0-flash",
    api_key=AGNES_API_KEY,
    temperature=0.3,
    max_tokens=2000
)

agent = BrowserAgent(lm=agnes_lm)
logger.info("✅ DSPy + Agnes агент готов!")

# ============================================================
# КОМАНДЫ ТЕЛЕГРАМ
# ============================================================

async def start(update, context):
    await update.message.reply_text(
        "🌐 Браузерный агент (DSPy + Agnes AI)\n\n"
        "📌 Команды:\n"
        "/ask <запрос> — выполнить задачу\n"
        "/skill <название> — использовать навык\n"
        "/skills — список навыков\n"
        "/image — последний скриншот\n"
        "/images — все скриншоты\n"
        "/log — скачать логи\n"
        "/stats — статистика агента\n\n"
        "🧠 Особенности:\n"
        "• Автоматическое создание навыков\n"
        "• Самовосстановление при ошибках\n"
        "• Структурированное планирование"
    )

async def ask(update, context):
    if not context.args:
        await update.message.reply_text("Пример: /ask сделай скриншот google.com")
        return
    
    user_query = " ".join(context.args)
    username = update.effective_user.username or "unknown"
    logger.info(f"👤 {username} запросил: {user_query}")
    
    status_msg = await update.message.reply_text("🧠 Думаю...")
    
    try:
        result = agent.forward(user_query)
        
        if result['success']:
            response = (
                f"✅ Готово!\n\n"
                f"📝 План:\n{result['plan'][:300]}\n\n"
                f"📤 Результат:\n{result['output'][:1500]}\n\n"
                f"🔄 Попыток: {result['retries'] + 1}"
            )
            if result['skill_created']:
                response += "\n🧠 Новый навык создан! Используй /skills"
            
            await status_msg.edit_text(response)
        else:
            await status_msg.edit_text(
                f"❌ Ошибка:\n{result['output'][:500]}\n\n"
                f"📝 План:\n{result['plan'][:200]}"
            )
            
    except Exception as e:
        logger.error(f"❌ Ошибка в /ask для {username}: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def skill_command(update, context):
    if not context.args:
        await update.message.reply_text("Пример: /skill open_google")
        return
    
    skill_name = context.args[0]
    result = agent.use_skill(skill_name)
    
    if result['success']:
        await update.message.reply_text(
            f"✅ Навык '{skill_name}' выполнен!\n\n"
            f"📤 {result['output'][:500]}"
        )
    else:
        await update.message.reply_text(
            f"❌ {result.get('error', 'Неизвестная ошибка')}"
        )

async def skills_list(update, context):
    if not agent.skills:
        await update.message.reply_text("📭 Навыков пока нет. Агент создаст их по мере работы.")
        return
    
    skills_text = "🧠 Доступные навыки:\n\n"
    for name, skill in agent.skills.items():
        desc = skill.get('description', 'Без описания')[:50]
        skills_text += f"• {name} — {desc}...\n"
    
    if len(skills_text) > 4000:
        skills_text = skills_text[:4000] + "\n\n... и ещё"
    
    await update.message.reply_text(skills_text)

async def stats(update, context):
    history = agnes_lm.get_history()
    
    stats_text = (
        f"📊 Статистика агента\n\n"
        f"🧠 Навыков: {len(agent.skills)}\n"
        f"💬 Вызовов Agnes AI: {len(history)}\n"
        f"🔄 Последних запросов: {len(history[-5:]) if history else 0}\n\n"
        f"📚 Последние навыки:\n"
    )
    
    for name in list(agent.skills.keys())[-5:]:
        stats_text += f"• {name}\n"
    
    await update.message.reply_text(stats_text)

async def log(update, context):
    try:
        log_file = os.path.join(LOGS_DIR, 'bot.log')
        if not os.path.exists(log_file):
            await update.message.reply_text("📭 Лог-файл не найден")
            return
        with open(log_file, 'rb') as f:
            await update.message.reply_document(document=f, filename='bot.log', caption=f"📋 Логи бота ({os.path.getsize(log_file)} байт)")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def image(update, context):
    try:
        screenshot_files = [f for f in os.listdir(SCREENSHOTS_DIR) if f.endswith('.png')]
        if not screenshot_files:
            await update.message.reply_text("📭 Скриншотов не найдено")
            return
        screenshot_files.sort(key=lambda x: os.path.getmtime(os.path.join(SCREENSHOTS_DIR, x)), reverse=True)
        latest = screenshot_files[0]
        file_path = os.path.join(SCREENSHOTS_DIR, latest)
        with open(file_path, 'rb') as f:
            await update.message.reply_photo(photo=f, caption=f"📸 {latest}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def images(update, context):
    try:
        screenshot_files = [f for f in os.listdir(SCREENSHOTS_DIR) if f.endswith('.png')]
        if not screenshot_files:
            await update.message.reply_text("📭 Скриншотов не найдено")
            return
        screenshot_files.sort(key=lambda x: os.path.getmtime(os.path.join(SCREENSHOTS_DIR, x)), reverse=True)
        sent_count = 0
        for s_file in screenshot_files[:10]:
            file_path = os.path.join(SCREENSHOTS_DIR, s_file)
            with open(file_path, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=f"📸 {s_file}")
            sent_count += 1
            await asyncio.sleep(0.5)
        if len(screenshot_files) > 10:
            await update.message.reply_text(f"📸 Показано 10 из {len(screenshot_files)} скриншотов")
        else:
            await update.message.reply_text(f"✅ Отправлено {sent_count} скриншотов")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("skill", skill_command))
    app.add_handler(CommandHandler("skills", skills_list))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("log", log))
    app.add_handler(CommandHandler("image", image))
    app.add_handler(CommandHandler("images", images))

    logger.info("🚀 Бот с DSPy + Agnes запущен!")
    logger.info(f"🧠 Загружено навыков: {len(agent.skills)}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()