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
import traceback
from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from PIL import Image

# ============================================================
# DSPy + Agnes
# ============================================================
import dspy
from dspy.teleprompt import BootstrapFewShot

warnings.filterwarnings("ignore")

# ============================================================
# НАСТРОЙКА ЛОГГИРОВАНИЯ (В КОНСОЛЬ)
# ============================================================

# Очищаем все существующие обработчики
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# Настройка логирования - ВСЁ В КОНСОЛЬ
logging.basicConfig(
    level=logging.DEBUG,  # DEBUG уровень для максимальной информации
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.StreamHandler(sys.stderr)  # Добавляем stderr для ошибок
    ],
    force=True  # Принудительная перезапись
)

# Отключаем лишние логи
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logging.getLogger("dspy").setLevel(logging.INFO)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Принудительный вывод в консоль
def log_debug(msg):
    print(f"🔍 {msg}", file=sys.stdout, flush=True)
    logger.debug(msg)

def log_info(msg):
    print(f"ℹ️ {msg}", file=sys.stdout, flush=True)
    logger.info(msg)

def log_error(msg):
    print(f"❌ {msg}", file=sys.stderr, flush=True)
    logger.error(msg)

# ============================================================
# НАСТРОЙКА ОКРУЖЕНИЯ
# ============================================================

log_info("=" * 60)
log_info("🚀 ЗАПУСК БОТА С DSPy + AGNES")
log_info("=" * 60)

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

log_info(f"✅ agent_workspace: {agent_workspace}")
log_info(f"✅ helpers_file: {helpers_file}")
log_info(f"✅ screenshots_dir: {SCREENSHOTS_DIR}")

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
    
    async def set_cookies_async():
        try:
            import httpx
            resp = httpx.get("http://localhost:9222/json/list", timeout=5.0)
            pages = resp.json()
            if not pages:
                log_error("❌ Нет активных вкладок")
                return False
            ws_url = pages[0]["webSocketDebuggerUrl"]
            log_info("🔗 Подключаюсь к WebSocket...")
            async with websockets.connect(ws_url) as ws:
                await ws.send(json.dumps({"id": 1, "method": "Network.setCookies", "params": {"cookies": COOKIES}}))
                response = json.loads(await ws.recv())
                if "error" in response:
                    log_error(f"❌ CDP ошибка: {response['error']}")
                    return False
                log_info(f"🍪 Установлено {len(COOKIES)} кук")
                return True
        except Exception as e:
            log_error(f"❌ Ошибка: {e}")
            traceback.print_exc()
            return False
    
    def set_cookies_global():
        try:
            loop = asyncio.get_running_loop()
            return asyncio.run_coroutine_threadsafe(set_cookies_async(), loop).result(timeout=10)
        except RuntimeError:
            return asyncio.run(set_cookies_async())
        except Exception as e:
            log_error(f"❌ Ошибка: {e}")
            traceback.print_exc()
            return False

except ImportError as e:
    log_error(f"⚠️ websockets не установлен: {e}")
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
            log_error("⚠️ Нет активных вкладок для установки размера")
            return False
        ws_url = pages[0]["webSocketDebuggerUrl"]
        log_info("🔗 Подключаюсь к WebSocket для установки размера...")
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
                log_error(f"⚠️ CDP ошибка: {response['error']}")
                return False
            log_info("✅ Размер окна установлен: 1280x720")
            return True
    except Exception as e:
        log_error(f"⚠️ Не удалось установить размер окна: {e}")
        traceback.print_exc()
        return False

def set_viewport_global():
    try:
        loop = asyncio.get_running_loop()
        return asyncio.run_coroutine_threadsafe(set_viewport_async(), loop).result(timeout=10)
    except RuntimeError:
        return asyncio.run(set_viewport_async())
    except Exception as e:
        log_error(f"⚠️ Не удалось установить размер окна: {e}")
        traceback.print_exc()
        return False

# ============================================================
# НАСТРОЙКА
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

if not TELEGRAM_TOKEN:
    log_error("❌ TELEGRAM_BOT_TOKEN не задан!")
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

os.environ["BU_CDP_URL"] = "http://localhost:9222"

log_info("🔄 Запускаю браузер...")
try:
    ensure_daemon()
    log_info("✅ Браузер готов")
except Exception as e:
    log_error(f"❌ Ошибка запуска браузера: {e}")
    traceback.print_exc()

log_info("🔄 Устанавливаю куки...")
set_cookies_global()

log_info("🔄 Устанавливаю размер окна...")
set_viewport_global()

# ============================================================
# AGNES LM ДЛЯ DSPy (ЧЕРЕЗ dspy.LM)
# ============================================================

class AgnesLM(dspy.LM):
    """Agnes AI через стандартный dspy.LM"""
    
    def __init__(self, model="agnes-2.0-flash", api_key=None, **kwargs):
        api_key = api_key or os.environ.get("AGNES_API_KEY")
        if not api_key:
            log_error("❌ AGNES_API_KEY не задан!")
            raise ValueError("AGNES_API_KEY не задан!")
        
        log_info(f"🔄 Инициализация Agnes LM (model: {model})...")
        
        try:
            super().__init__(
                model=model,
                api_key=api_key,
                api_base="https://apihub.agnes-ai.com/v1",
                temperature=kwargs.get("temperature", 0.3),
                max_tokens=kwargs.get("max_tokens", 2000),
                **kwargs
            )
            log_info(f"✅ Agnes LM инициализирован через dspy.LM (model: {model})")
        except Exception as e:
            log_error(f"❌ Ошибка инициализации Agnes LM: {e}")
            traceback.print_exc()
            raise
        
        self.history = []
    
    def __call__(self, prompt, **kwargs):
        log_info(f"📤 Запрос к Agnes AI: {str(prompt)[:100]}...")
        try:
            result = super().__call__(prompt, **kwargs)
            self.history.append({
                "prompt": prompt,
                "response": result,
                "timestamp": time.time()
            })
            log_info(f"📥 Ответ Agnes AI: {str(result)[:100]}...")
            return result
        except Exception as e:
            log_error(f"❌ Ошибка вызова Agnes AI: {e}")
            traceback.print_exc()
            raise
    
    def get_history(self):
        return self.history
    
    def clear_history(self):
        self.history = []

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
        
        log_info("🔄 Инициализация BrowserAgent...")
        
        try:
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
            
            log_info("✅ DSPy + Agnes агент инициализирован")
            log_info(f"📚 Загружено навыков: {len(self.skills)}")
        except Exception as e:
            log_error(f"❌ Ошибка инициализации агента: {e}")
            traceback.print_exc()
            raise
    
    def _load_skills(self):
        skills_dir = os.path.join(agent_workspace, "domain-skills")
        if not os.path.exists(skills_dir):
            log_info("📭 Папка навыков не найдена, создаю новую...")
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
                                log_info(f"📄 Загружен навык: {skill_name}")
                        except Exception as e:
                            log_error(f"⚠️ Не удалось загрузить навык {f}: {e}")
    
    def forward(self, user_query: str, max_retries: int = 3):
        log_info("=" * 60)
        log_info(f"🤔 НОВАЯ ЗАДАЧА: {user_query}")
        log_info("=" * 60)
        
        try:
            log_info("📝 Шаг 1: Планирование...")
            plan_result = self.planner(user_query=user_query)
            
            plan = plan_result.plan
            code = plan_result.code
            explanation = plan_result.explanation
            
            log_info(f"📋 План:\n{plan}")
            log_info(f"💻 Сгенерированный код:\n{code}")
            log_info(f"📖 Объяснение:\n{explanation}")
            
            log_info("⚙️ Шаг 2: Выполнение кода...")
            output, success = self._execute_code(code)
            
            attempt = 0
            while not success and attempt < max_retries:
                log_info(f"🔧 Шаг 3: Исправление ошибки (попытка {attempt + 1}/{max_retries})")
                log_error(f"❌ Ошибка: {output}")
                
                fix_result = self.fixer(
                    error=output,
                    broken_code=code
                )
                
                code = fix_result.fixed_code
                log_info(f"🔄 Исправленный код:\n{code}")
                log_info(f"📖 Объяснение исправления:\n{fix_result.explanation}")
                
                log_info("⚙️ Повторное выполнение...")
                output, success = self._execute_code(code)
                attempt += 1
            
            skill_created = False
            if success:
                log_info("✅ Код выполнен успешно!")
                log_info(f"📤 Вывод:\n{output}")
                
                if len(code) > 50:
                    log_info("🧠 Шаг 4: Создание навыка...")
                    skill = self._extract_skill(user_query, code)
                    if skill:
                        self.skills[skill['name']] = skill
                        self._save_skill(skill)
                        skill_created = True
                        log_info(f"✅ Навык создан: {skill['name']}")
            else:
                log_error(f"❌ Код не выполнен после {attempt} попыток")
                log_error(f"❌ Последняя ошибка: {output}")
            
            log_info("=" * 60)
            log_info(f"📊 РЕЗУЛЬТАТ: {'УСПЕШНО' if success else 'ОШИБКА'}")
            log_info(f"🔄 Попыток: {attempt + 1}")
            log_info(f"🧠 Навык создан: {'ДА' if skill_created else 'НЕТ'}")
            log_info("=" * 60)
            
            return {
                "success": success,
                "plan": plan,
                "code": code,
                "output": output,
                "explanation": explanation,
                "retries": attempt,
                "skill_created": skill_created
            }
        except Exception as e:
            log_error(f"❌ Критическая ошибка в forward: {e}")
            traceback.print_exc()
            return {
                "success": False,
                "plan": "Ошибка планирования",
                "code": "",
                "output": str(e),
                "explanation": traceback.format_exc(),
                "retries": 0,
                "skill_created": False
            }
    
    def _execute_code(self, code: str):
        return execute_code(code)
    
    def _extract_skill(self, user_query: str, code: str):
        try:
            log_info("🧠 Извлечение навыка из решения...")
            result = self.skill_extractor(
                user_query=user_query,
                code=code
            )
            
            skill = {
                "name": result.skill_name.lower().replace(" ", "_"),
                "description": result.skill_description,
                "code": result.skill_code,
                "domain": "auto"
            }
            
            log_info(f"📝 Название навыка: {skill['name']}")
            log_info(f"📝 Описание: {skill['description'][:100]}...")
            
            return skill
        except Exception as e:
            log_error(f"⚠️ Не удалось извлечь навык: {e}")
            traceback.print_exc()
            return None
    
    def _save_skill(self, skill: dict):
        try:
            skills_dir = os.path.join(agent_workspace, "domain-skills", skill.get("domain", "auto"))
            os.makedirs(skills_dir, exist_ok=True)
            
            skill_path = os.path.join(skills_dir, f"{skill['name']}.md")
            
            content = f"# {skill['name']}\n\n**Описание:** {skill.get('description', 'Автоматически созданный навык')}\n\n**Код:**\n```python\n{skill['code']}\n```\n"
            
            with open(skill_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            log_info(f"✅ Навык сохранён локально: {skill_path}")
            
            push_to_github(content, f"{skill['name']}.md", skill.get("domain", "auto"))
            
        except Exception as e:
            log_error(f"❌ Ошибка сохранения навыка: {e}")
            traceback.print_exc()
    
    def use_skill(self, skill_name: str) -> dict:
        log_info(f"🎯 Использование навыка: {skill_name}")
        
        try:
            if skill_name in self.skills:
                skill = self.skills[skill_name]
                
                if 'code' in skill:
                    log_info("⚙️ Выполнение кода навыка...")
                    output, success = self._execute_code(skill['code'])
                    log_info(f"✅ Навык выполнен: {success}")
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
                        log_error(f"❌ Ошибка загрузки навыка: {e}")
                        traceback.print_exc()
                        return {
                            "success": False,
                            "error": f"Ошибка загрузки навыка: {e}"
                        }
            
            log_error(f"❌ Навык не найден: {skill_name}")
            return {
                "success": False,
                "error": f"Навык '{skill_name}' не найден"
            }
        except Exception as e:
            log_error(f"❌ Ошибка использования навыка: {e}")
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }

# ============================================================
# GITHUB
# ============================================================

def push_to_github(content, filename, host="x.com"):
    if not GITHUB_TOKEN:
        log_error("⚠️ GITHUB_TOKEN не задан, навык не будет отправлен в GitHub")
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
            log_info(f"✅ Навык отправлен в GitHub: {file_path}")
            return True
        else:
            log_error(f"❌ Ошибка отправки в GitHub: {response.text}")
            return False
    except Exception as e:
        log_error(f"❌ Ошибка при отправке в GitHub: {e}")
        traceback.print_exc()
        return False

def push_helpers_to_github():
    if not GITHUB_TOKEN:
        log_error("⚠️ GITHUB_TOKEN не задан, helpers не будут отправлены")
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
        log_error("⚠️ agent_helpers.py не найден")
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
            log_info(f"✅ agent_helpers.py отправлен в GitHub")
            return True
        else:
            log_error(f"❌ Ошибка отправки helpers: {response.text}")
            return False
    except Exception as e:
        log_error(f"❌ Ошибка при отправке helpers: {e}")
        traceback.print_exc()
        return False

# ============================================================
# ВЫПОЛНИТЕЛЬ КОДА
# ============================================================

def execute_code(code):
    log_info(f"⚙️ ВЫПОЛНЕНИЕ КОДА:\n{code}")
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
            
            log_info(f"✅ Навык сохранён локально: {skill_path}")
            
            push_to_github(content, f"{name}.md", host)
            
            return skill_path
        
        def add_helper(code):
            helpers_path = os.path.join(agent_workspace, "agent_helpers.py")
            
            if not os.path.exists(helpers_path):
                with open(helpers_path, "w") as f:
                    f.write('"""Agent-editable browser helpers."""\n')
            
            with open(helpers_path, "a", encoding='utf-8') as f:
                f.write(f"\n\n{code}\n")
            
            log_info(f"✅ Helper добавлен в agent_helpers.py")
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
            log_info(f"📸 Сохраняю скриншот в: {full_path}")
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
            log_info(f"📤 ВЫВОД КОДА:\n{output}")
            return output.strip(), True
        elif 'result' in globals_dict:
            result = str(globals_dict['result'])
            log_info(f"📤 РЕЗУЛЬТАТ: {result}")
            return result, True
        
        log_error("⚠️ Код выполнен, но нет вывода")
        return "⚠️ Код выполнен, но нет вывода. Добавьте print() в код.", False
    except Exception as e:
        log_error(f"❌ Ошибка выполнения: {e}")
        traceback.print_exc()
        return str(e), False

# ============================================================
# ИНИЦИАЛИЗАЦИЯ DSPy АГЕНТА
# ============================================================

try:
    log_info("🔄 Инициализация Agnes LM...")
    agnes_lm = AgnesLM(
        model="agnes-2.0-flash",
        api_key=AGNES_API_KEY,
        temperature=0.3,
        max_tokens=2000
    )
except Exception as e:
    log_error(f"❌ Критическая ошибка инициализации Agnes LM: {e}")
    traceback.print_exc()
    sys.exit(1)

try:
    log_info("🔄 Инициализация BrowserAgent...")
    agent = BrowserAgent(lm=agnes_lm)
except Exception as e:
    log_error(f"❌ Критическая ошибка инициализации агента: {e}")
    traceback.print_exc()
    sys.exit(1)

log_info("=" * 60)
log_info("✅ DSPy + Agnes агент готов к работе!")
log_info("=" * 60)

# ============================================================
# КОМАНДЫ ТЕЛЕГРАМ
# ============================================================

async def start(update, context):
    try:
        username = update.effective_user.username or "unknown"
        log_info(f"👤 Пользователь {username} вызвал /start")
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
    except Exception as e:
        log_error(f"❌ Ошибка в start: {e}")
        traceback.print_exc()

async def ask(update, context):
    try:
        if not context.args:
            await update.message.reply_text("Пример: /ask сделай скриншот google.com")
            return
        
        user_query = " ".join(context.args)
        username = update.effective_user.username or "unknown"
        user_id = update.effective_user.id
        
        log_info("=" * 60)
        log_info(f"📩 НОВЫЙ ЗАПРОС ОТ @{username} (ID: {user_id})")
        log_info(f"📝 Текст: {user_query}")
        log_info("=" * 60)
        
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
                
                log_info(f"✅ Успешный ответ для @{username}")
                await status_msg.edit_text(response)
            else:
                log_error(f"❌ Ошибка выполнения для @{username}: {result['output'][:200]}")
                await status_msg.edit_text(
                    f"❌ Ошибка:\n{result['output'][:500]}\n\n"
                    f"📝 План:\n{result['plan'][:200]}"
                )
                
        except Exception as e:
            log_error(f"❌ Ошибка обработки для @{username}: {e}")
            traceback.print_exc()
            await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
            
    except Exception as e:
        log_error(f"❌ Критическая ошибка в ask: {e}")
        traceback.print_exc()

async def skill_command(update, context):
    try:
        if not context.args:
            await update.message.reply_text("Пример: /skill open_google")
            return
        
        skill_name = context.args[0]
        username = update.effective_user.username or "unknown"
        
        log_info(f"🎯 @{username} использует навык: {skill_name}")
        
        result = agent.use_skill(skill_name)
        
        if result['success']:
            log_info(f"✅ Навык {skill_name} выполнен для @{username}")
            await update.message.reply_text(
                f"✅ Навык '{skill_name}' выполнен!\n\n"
                f"📤 {result['output'][:500]}"
            )
        else:
            log_error(f"❌ Ошибка выполнения навыка {skill_name} для @{username}: {result.get('error', 'Unknown')}")
            await update.message.reply_text(
                f"❌ {result.get('error', 'Неизвестная ошибка')}"
            )
    except Exception as e:
        log_error(f"❌ Ошибка в skill_command: {e}")
        traceback.print_exc()

async def skills_list(update, context):
    try:
        username = update.effective_user.username or "unknown"
        log_info(f"📚 @{username} запросил список навыков")
        
        if not agent.skills:
            await update.message.reply_text("📭 Навыков пока нет. Агент создаст их по мере работы.")
            return
        
        skills_text = "🧠 Доступные навыки:\n\n"
        for name, skill in agent.skills.items():
            desc = skill.get('description', 'Без описания')[:50]
            skills_text += f"• {name} — {desc}...\n"
        
        if len(skills_text) > 4000:
            skills_text = skills_text[:4000] + "\n\n... и ещё"
        
        log_info(f"📚 Отправлено {len(agent.skills)} навыков для @{username}")
        await update.message.reply_text(skills_text)
    except Exception as e:
        log_error(f"❌ Ошибка в skills_list: {e}")
        traceback.print_exc()

async def stats(update, context):
    try:
        username = update.effective_user.username or "unknown"
        log_info(f"📊 @{username} запросил статистику")
        
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
    except Exception as e:
        log_error(f"❌ Ошибка в stats: {e}")
        traceback.print_exc()

async def log(update, context):
    try:
        username = update.effective_user.username or "unknown"
        log_info(f"📄 @{username} скачивает логи")
        
        log_file = os.path.join(LOGS_DIR, 'bot.log')
        if not os.path.exists(log_file):
            await update.message.reply_text("📭 Лог-файл не найден")
            return
        with open(log_file, 'rb') as f:
            await update.message.reply_document(document=f, filename='bot.log', caption=f"📋 Логи бота ({os.path.getsize(log_file)} байт)")
    except Exception as e:
        log_error(f"❌ Ошибка отправки логов для @{username}: {e}")
        traceback.print_exc()

async def image(update, context):
    try:
        username = update.effective_user.username or "unknown"
        log_info(f"📸 @{username} запросил последний скриншот")
        
        screenshot_files = [f for f in os.listdir(SCREENSHOTS_DIR) if f.endswith('.png')]
        if not screenshot_files:
            await update.message.reply_text("📭 Скриншотов не найдено")
            return
        screenshot_files.sort(key=lambda x: os.path.getmtime(os.path.join(SCREENSHOTS_DIR, x)), reverse=True)
        latest = screenshot_files[0]
        file_path = os.path.join(SCREENSHOTS_DIR, latest)
        with open(file_path, 'rb') as f:
            await update.message.reply_photo(photo=f, caption=f"📸 {latest}")
        log_info(f"✅ Отправлен скриншот {latest} для @{username}")
    except Exception as e:
        log_error(f"❌ Ошибка отправки скриншота для @{username}: {e}")
        traceback.print_exc()

async def images(update, context):
    try:
        username = update.effective_user.username or "unknown"
        log_info(f"📸 @{username} запросил все скриншоты")
        
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
        log_info(f"✅ Отправлено {sent_count} скриншотов для @{username}")
    except Exception as e:
        log_error(f"❌ Ошибка отправки скриншотов для @{username}: {e}")
        traceback.print_exc()

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    try:
        log_info("=" * 60)
        log_info("🚀 ЗАПУСК TELEGRAM БОТА")
        log_info("=" * 60)
        
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("ask", ask))
        app.add_handler(CommandHandler("skill", skill_command))
        app.add_handler(CommandHandler("skills", skills_list))
        app.add_handler(CommandHandler("stats", stats))
        app.add_handler(CommandHandler("log", log))
        app.add_handler(CommandHandler("image", image))
        app.add_handler(CommandHandler("images", images))

        log_info("=" * 60)
        log_info("✅ БОТ ГОТОВ К РАБОТЕ!")
        log_info(f"🧠 Загружено навыков: {len(agent.skills)}")
        log_info(f"📁 Скриншоты: {SCREENSHOTS_DIR}")
        log_info(f"📁 Логи: {LOGS_DIR}")
        log_info("=" * 60)
        
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        log_error(f"❌ Критическая ошибка запуска: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()