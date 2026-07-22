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
import importlib
import pickle
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from promt import SYSTEM_PROMPT
from PIL import Image
from browser_harness.helpers import (
    new_tab, goto_url, wait_for_load, page_info, capture_screenshot,
    click_at_xy, type_text, press_key, scroll, js, cdp, ensure_real_tab,
    wait_for_element, list_tabs, current_tab, close_tab, switch_tab,
    fill_input, upload_file, http_get, drain_events
)
from browser_harness.admin import ensure_daemon

warnings.filterwarnings("ignore")

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
MEMORY_DIR = '/app/memory'
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(MEMORY_DIR, exist_ok=True)

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

logger = logging.getLogger(__name__)
logger.info(f"✅ agent_workspace: {agent_workspace}")
logger.info(f"✅ helpers_file: {helpers_file}")
logger.info(f"✅ screenshots_dir: {SCREENSHOTS_DIR}")
logger.info(f"✅ memory_dir: {MEMORY_DIR}")

# ============================================================
# ДОЛГОСРОЧНАЯ ПАМЯТЬ
# ============================================================

class Memory:
    def __init__(self, memory_dir):
        self.memory_dir = memory_dir
        self.data = {
            'skills': {},
            'helpers': [],
            'patterns': [],
            'stats': {
                'tasks_done': 0,
                'helpers_written': 0,
                'skills_saved': 0,
                'success_rate': 0
            }
        }
        self.load()
    
    def load(self):
        memory_file = os.path.join(self.memory_dir, 'memory.pkl')
        if os.path.exists(memory_file):
            try:
                with open(memory_file, 'rb') as f:
                    self.data = pickle.load(f)
                logger.info(f"✅ Память загружена: {len(self.data['skills'])} навыков")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось загрузить память: {e}")
    
    def save(self):
        memory_file = os.path.join(self.memory_dir, 'memory.pkl')
        try:
            with open(memory_file, 'wb') as f:
                pickle.dump(self.data, f)
            logger.info(f"💾 Память сохранена")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения памяти: {e}")
    
    def add_skill(self, host, name):
        if host not in self.data['skills']:
            self.data['skills'][host] = []
        if name not in self.data['skills'][host]:
            self.data['skills'][host].append(name)
            self.data['stats']['skills_saved'] += 1
            self.save()
            return True
        return False
    
    def get_skills(self, host):
        return self.data['skills'].get(host, [])
    
    def add_helper(self, name):
        if name not in self.data['helpers']:
            self.data['helpers'].append(name)
            self.data['stats']['helpers_written'] += 1
            self.save()
            return True
        return False
    
    def add_task(self, success=True):
        self.data['stats']['tasks_done'] += 1
        total = self.data['stats']['tasks_done']
        successful = self.data['stats'].get('successful_tasks', 0)
        if success:
            self.data['stats']['successful_tasks'] = successful + 1
        self.data['stats']['success_rate'] = int((successful / total) * 100) if total > 0 else 0
        self.save()
    
    def get_summary(self):
        return {
            'tasks': self.data['stats']['tasks_done'],
            'helpers': len(self.data['helpers']),
            'skills': sum(len(v) for v in self.data['skills'].values()),
            'patterns': len(self.data['patterns']),
            'success_rate': self.data['stats']['success_rate'],
            'domains': list(self.data['skills'].keys())
        }

# ============================================================
# ПОСТОЯННАЯ СЕССИЯ АГЕНТА
# ============================================================

class AgentSession:
    def __init__(self, workspace, memory):
        self.workspace = workspace
        self.memory = memory
        self.helpers = {}
        self.base_functions = {
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
            'wait_for_element': wait_for_element,
            'list_tabs': list_tabs,
            'current_tab': current_tab,
            'close_tab': close_tab,
            'switch_tab': switch_tab,
            'fill_input': fill_input,
            'upload_file': upload_file,
            'http_get': http_get,
            'drain_events': drain_events,
            'time': time,
            'json': json,
        }
        self.load_helpers()
        logger.info("🧠 AgentSession создан")
    
    def load_helpers(self):
        helpers_path = os.path.join(self.workspace, "agent_helpers.py")
        if os.path.exists(helpers_path):
            sys.path.insert(0, self.workspace)
            if 'agent_helpers' in sys.modules:
                importlib.reload(sys.modules['agent_helpers'])
            else:
                import agent_helpers
            self.helpers = {}
            for name in dir(agent_helpers):
                if not name.startswith('_'):
                    attr = getattr(agent_helpers, name)
                    if callable(attr):
                        self.helpers[name] = attr
            logger.info(f"✅ Загружено {len(self.helpers)} helpers из agent_helpers.py")
        else:
            logger.info("ℹ️ agent_helpers.py не найден, создаю пустой")
            with open(helpers_path, "w") as f:
                f.write('"""Agent-editable browser helpers."""\n')
    
    def get_functions(self):
        funcs = self.base_functions.copy()
        funcs.update(self.helpers)
        return funcs
    
    def add_helper(self, code, name=None):
        helpers_path = os.path.join(self.workspace, "agent_helpers.py")
        with open(helpers_path, "a", encoding='utf-8') as f:
            f.write(f"\n\n{code}\n")
        self.load_helpers()
        if name:
            self.memory.add_helper(name)
        logger.info(f"✅ Helper добавлен в agent_helpers.py")
        return True
    
    def execute(self, code, globals_dict=None):
        if globals_dict is None:
            globals_dict = {}
        full_globals = self.get_functions()
        full_globals.update(globals_dict)
        full_globals['print'] = print
        full_globals['__builtins__'] = __builtins__
        full_globals['session'] = self
        full_globals['memory'] = self.memory
        full_globals['add_helper'] = self.add_helper
        full_globals['save_skill'] = globals_dict.get('save_skill')
        stdout_buffer = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = stdout_buffer
        try:
            exec(code, full_globals)
            output = stdout_buffer.getvalue()
            return output, True, full_globals
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения: {e}")
            return str(e), False, full_globals
        finally:
            sys.stdout = old_stdout

_agent_session = None
_memory = None

def get_memory():
    global _memory
    if _memory is None:
        _memory = Memory(MEMORY_DIR)
    return _memory

def get_session():
    global _agent_session
    if _agent_session is None:
        _agent_session = AgentSession(agent_workspace, get_memory())
    return _agent_session

memory = get_memory()
session = get_session()

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

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

os.environ["BU_CDP_URL"] = "http://localhost:9222"
ensure_daemon()
logger.info("✅ Браузер готов")

set_cookies_global()
set_viewport_global()

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

AGNES_IMAGE_API_URL = "https://apihub.agnes-ai.com/v1/images/generations"

def get_image_size(image_data):
    try:
        img = Image.open(io.BytesIO(image_data))
        width, height = img.size
        logger.info(f"📐 Размер изображения: {width}x{height}")
        return width, height
    except Exception as e:
        logger.error(f"Ошибка при определении размера: {e}")
        return None, None

def replace_background(image_data, new_background_prompt: str):
    if not AGNES_API_KEY:
        return None, "AGNES_API_KEY не установлен!"
    
    if not image_data:
        return None, "Нет данных изображения"
    
    if not new_background_prompt or len(new_background_prompt.strip()) < 2:
        return None, "Слишком короткое описание фона"
    
    try:
        width, height = get_image_size(image_data)
        MAX_SIZE = 1024
        MIN_SIZE = 256
        if width and height:
            if width > MAX_SIZE or height > MAX_SIZE:
                ratio = min(MAX_SIZE / width, MAX_SIZE / height)
                width = int(width * ratio)
                height = int(height * ratio)
            if width < MIN_SIZE or height < MIN_SIZE:
                ratio = max(MIN_SIZE / width, MIN_SIZE / height)
                width = int(width * ratio)
                height = int(height * ratio)
            size = f"{width}x{height}"
        else:
            size = "1024x1024"
            logger.warning("⚠️ Использую стандартный размер: 1024x1024")
        
        logger.info(f"📐 Размер для API: {size}")
        
        try:
            img = Image.open(io.BytesIO(image_data))
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85, optimize=True)
            image_data = buffer.getvalue()
        except Exception as e:
            logger.warning(f"Не удалось оптимизировать изображение: {e}")
        
        img_b64 = base64.b64encode(image_data).decode('utf-8')
        data_uri = f"data:image/jpeg;base64,{img_b64}"
        
        enhanced_prompt = f"""
        Replace the background with: {new_background_prompt}.
        Keep the main subject exactly as is.
        Maintain the original lighting and shadows.
        Make the background look natural and realistic.
        Do not alter the main subject.
        """
        
        headers = {
            "Authorization": f"Bearer {AGNES_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "agnes-image-2.0-flash",
            "prompt": enhanced_prompt.strip(),
            "size": size,
            "extra_body": {
                "image": [data_uri],
                "response_format": "url"
            }
        }
        
        logger.info(f"📤 Отправка запроса к Agnes AI...")
        logger.info(f"   Промпт: {new_background_prompt[:50]}...")
        
        with httpx.Client(timeout=90.0) as client:
            response = client.post(
                AGNES_IMAGE_API_URL,
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            result = response.json()
        
        logger.info("✅ Изображение сгенерировано")
        
        if 'data' in result and len(result['data']) > 0:
            if 'url' in result['data'][0]:
                return result['data'][0]['url'], None
            elif 'b64_json' in result['data'][0]:
                return result['data'][0]['b64_json'], None
        
        logger.error(f"❌ Неожиданный ответ: {result}")
        return None, "Неожиданный формат ответа от API"
        
    except httpx.TimeoutException:
        return None, "⏰ Превышено время ожидания (90 секунд)"
    except httpx.HTTPStatusError as e:
        status = e.response.status_code if e.response else "unknown"
        return None, f"HTTP ошибка {status}: {str(e)}"
    except httpx.RequestError as e:
        logger.error(f"❌ Ошибка запроса: {e}")
        return None, f"Ошибка сети: {str(e)}"
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return None, f"Внутренняя ошибка: {str(e)[:100]}"

async def ask_agnes(messages):
    logger.info("=" * 60)
    logger.info("📤 ОТПРАВКА В AGNES AI:")
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        logger.info(f"  [{role}]: {content[:500]}..." if len(content) > 500 else f"  [{role}]: {content}")
    logger.info("=" * 60)
    
    headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "agnes-2.0-flash",
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 2000
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post("https://apihub.agnes-ai.com/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"❌ Ошибка Agnes AI: {e}")
        return f"Ошибка LLM: {str(e)[:200]}"

def execute_code(code):
    logger.info(f"⚙️ ВЫПОЛНЕНИЕ КОДА:\n{code}")
    session = get_session()
    memory = get_memory()
    
    def save_skill(host, name, content):
        skills_dir = os.path.join(agent_workspace, "domain-skills", host)
        os.makedirs(skills_dir, exist_ok=True)
        os.chmod(skills_dir, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        skill_path = os.path.join(skills_dir, f"{name}.md")
        with open(skill_path, "w", encoding='utf-8') as f:
            f.write(content)
        os.chmod(skill_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)
        logger.info(f"✅ Навык сохранён локально: {skill_path}")
        memory.add_skill(host, name)
        push_to_github(content, f"{name}.md", host)
        return skill_path
    
    def add_helper(code, name=None):
        return session.add_helper(code, name)
    
    globals_dict = {
        'save_skill': save_skill,
        'add_helper': add_helper,
        'session': session,
        'memory': memory,
        'time': time,
        'json': json,
        'print': print,
        '__builtins__': __builtins__,
    }
    
    output, success, result_globals = session.execute(code, globals_dict)
    memory.add_task(success)
    if success:
        logger.info(f"📤 ВЫВОД КОДА:\n{output}")
        return output.strip(), True
    else:
        logger.error(f"❌ Ошибка выполнения: {output}")
        return output, False

# ============================================================
# КОМАНДЫ
# ============================================================

async def start(update, context):
    await update.message.reply_text(
        "🌐 Браузер:\n"
        "/ask <запрос> — задать задачу агенту\n"
        "/run — открыть псевдо-терминал\n"
        "/run [файл.json] — выполнить код из JSON → ответ JSON\n"
        "/tweets — получить последние 10 твитов в JSON\n"
        "/image — последний скриншот\n"
        "/images — все скриншоты\n"
        "/skills — список навыков\n"
        "/memory — показать память агента\n"
        "/log — скачать логи\n\n"
        "🎨 Фотошоп:\n"
        "/bg <описание> — заменить фон\n"
        "/clear — очистить кэш"
    )

# ============================================================
# ПСЕВДО-ТЕРМИНАЛ С JSON
# ============================================================

async def run_command(update, context):
    """Выполняет код из текста или JSON-файла, возвращает JSON"""
    
    # Проверяем, есть ли вложенный файл
    if update.message.document:
        file = await update.message.document.get_file()
        file_content = await file.download_as_bytearray()
        file_name = update.message.document.file_name
        
        if file_name.endswith('.json'):
            try:
                data = json.loads(file_content)
                if isinstance(data, dict) and 'code' in data:
                    code = data['code']
                elif isinstance(data, list):
                    code = '\n'.join(str(item) for item in data)
                else:
                    code = json.dumps(data, indent=2)
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка парсинга JSON: {e}")
                return
        else:
            # Если не JSON — выполняем как код
            code = file_content.decode('utf-8')
        
        output, success = execute_code(code)
        
        # Отправляем результат как JSON
        result = {
            "success": success,
            "output": output[:4000] if success else output,
            "code": code[:500] if len(code) > 500 else code
        }
        
        json_file = "/app/result.json"
        with open(json_file, "w", encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        await update.message.reply_document(
            document=open(json_file, "rb"),
            filename="result.json",
            caption="📊 Результат выполнения"
        )
        return
    
    # Если нет файла — обычный режим терминала
    if context.user_data.get('terminal_mode'):
        if update.message.text and update.message.text != '/run':
            code = update.message.text
            context.user_data['terminal_mode'] = False
            output, success = execute_code(code)
            
            result = {
                "success": success,
                "output": output[:4000] if success else output,
                "code": code[:500] if len(code) > 500 else code
            }
            
            json_file = "/app/result.json"
            with open(json_file, "w", encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            await update.message.reply_document(
                document=open(json_file, "rb"),
                filename="result.json",
                caption="📊 Результат выполнения"
            )
            return
    
    context.user_data['terminal_mode'] = True
    context.user_data['terminal_buffer'] = []
    await update.message.reply_text(
        "💻 **Псевдо-терминал**\n"
        "Введи Python код строка за строкой.\n"
        "Или отправь **JSON-файл** с ключом `code`.\n"
        "Для выполнения отправь **`exit`** или **`run`**.\n"
        "Для отмены отправь **`cancel`**.\n\n"
        "📝 Вводи код:",
        parse_mode='Markdown'
    )

async def handle_terminal_input(update, context):
    """Обрабатывает ввод в псевдо-терминале"""
    if not context.user_data.get('terminal_mode'):
        return
    
    text = update.message.text.strip()
    
    # Команды
    if text.lower() == 'exit' or text.lower() == 'run':
        code = '\n'.join(context.user_data.get('terminal_buffer', []))
        context.user_data['terminal_mode'] = False
        context.user_data['terminal_buffer'] = []
        
        if code.strip():
            await update.message.reply_text("⚙️ Выполняю код...")
            output, success = execute_code(code)
            
            result = {
                "success": success,
                "output": output[:4000] if success else output,
                "code": code[:500] if len(code) > 500 else code
            }
            
            json_file = "/app/result.json"
            with open(json_file, "w", encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            await update.message.reply_document(
                document=open(json_file, "rb"),
                filename="result.json",
                caption="📊 Результат выполнения"
            )
        else:
            await update.message.reply_text("❌ Код пустой. Отмена.")
        return
    
    if text.lower() == 'cancel':
        context.user_data['terminal_mode'] = False
        context.user_data['terminal_buffer'] = []
        await update.message.reply_text("🛑 Терминал закрыт.")
        return
    
    # Добавляем строку в буфер
    if 'terminal_buffer' not in context.user_data:
        context.user_data['terminal_buffer'] = []
    context.user_data['terminal_buffer'].append(text)
    
    # Показываем текущий код
    current_code = '\n'.join(context.user_data['terminal_buffer'])
    await update.message.reply_text(
        f"📝 Добавлено:\n```python\n{current_code}\n```\n"
        f"Продолжай ввод или отправь **exit** для выполнения.",
        parse_mode='Markdown'
    )

# ============================================================
# ОСТАЛЬНЫЕ КОМАНДЫ
# ============================================================

async def tweets_command(update, context):
    """Извлекает твиты и отправляет JSON-файлом"""
    await update.message.reply_text("📊 Извлекаю последние твиты...")
    
    code = """
new_tab("https://x.com")
wait_for_load()
time.sleep(5)

js_code = \"\"\"
Array.from(document.querySelectorAll('article[data-testid="tweet"]'))
    .slice(0, 10)
    .map(t => ({
        text: t.querySelector('[data-testid="tweetText"]')?.innerText || '',
        author: t.querySelector('[data-testid="User-Name"]')?.innerText || '',
        likes: t.querySelector('[data-testid="like"]')?.getAttribute('aria-label') || '0'
    }))
\"\"\"

tweets = js(js_code)

import json
with open("/app/tweets.json", "w", encoding='utf-8') as f:
    json.dump(tweets, f, indent=2, ensure_ascii=False)

print(f"✅ Найдено твитов: {len(tweets)}")
print(json.dumps(tweets, indent=2, ensure_ascii=False))
"""

    output, success = execute_code(code)
    
    if success:
        try:
            with open("/app/tweets.json", "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename="tweets.json",
                    caption=f"📊 {output[:200]}"
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
    else:
        await update.message.reply_text(f"❌ Ошибка:\n{output[:4000]}")

async def memory_command(update, context):
    memory = get_memory()
    summary = memory.get_summary()
    
    text = f"""
🧠 **Память агента**

📊 **Статистика:**
• Выполнено задач: {summary['tasks']}
• Успешность: {summary['success_rate']}%
• Помощников (helpers): {summary['helpers']}
• Навыков: {summary['skills']}
• Паттернов: {summary['patterns']}

🌐 **Домены с навыками:**
"""
    if summary['domains']:
        for domain in summary['domains']:
            skills = memory.get_skills(domain)
            text += f"  • {domain}: {', '.join(skills) if skills else 'нет навыков'}\n"
    else:
        text += "  • пока нет\n"
    
    await update.message.reply_text(text)

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

async def skills(update, context):
    try:
        skills_dir = os.path.join(agent_workspace, "domain-skills")
        if not os.path.exists(skills_dir):
            await update.message.reply_text("📭 Папка с навыками не найдена")
            return
        
        skills_list = []
        for domain in os.listdir(skills_dir):
            domain_path = os.path.join(skills_dir, domain)
            if os.path.isdir(domain_path):
                for f in os.listdir(domain_path):
                    if f.endswith(".md") or f.endswith(".txt"):
                        skills_list.append(f"{domain}/{f}")
        
        if skills_list:
            msg = "🧠 **Доступные навыки:**\n\n"
            for skill in skills_list[:20]:
                msg += f"• `{skill}`\n"
            if len(skills_list) > 20:
                msg += f"\n... и ещё {len(skills_list) - 20}"
            await update.message.reply_text(msg, parse_mode='Markdown')
        else:
            await update.message.reply_text("🧠 Навыков пока нет. Агент создаст их по мере работы.")
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

async def ask(update, context):
    if not context.args:
        await update.message.reply_text("Пример: /ask сделай скриншот google.com")
        return

    user_query = " ".join(context.args)
    username = update.effective_user.username or "unknown"
    logger.info(f"👤 {username} запросил: {user_query}")
    
    status_msg = await update.message.reply_text("🤔 Думаю...")

    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_query}
        ]

        response = await ask_agnes(messages)

        if "```python" in response:
            code_match = re.search(r'```python\n(.*?)\n```', response, re.DOTALL)
            code = code_match.group(1) if code_match else response

            await status_msg.edit_text("⚙️ Выполняю код...")
            output, success = execute_code(code)

            if not success:
                await status_msg.edit_text(f"❌ {output}")
            else:
                logger.info(f"✅ Успешное выполнение для {username}")
                await status_msg.edit_text(f"✅ Результат:\n{output[:4000]}")
        else:
            logger.info(f"💬 Ответ без кода для {username}: {response[:100]}...")
            await status_msg.edit_text(response[:4000])

    except Exception as e:
        logger.error(f"❌ Ошибка в /ask для {username}: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'last_image' in context.user_data:
        del context.user_data['last_image']
        await update.message.reply_text("🧹 Кэш очищен!")
    else:
        await update.message.reply_text("📭 Кэш пуст")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        context.user_data['last_image'] = bytes(photo_bytes)
        width, height = get_image_size(photo_bytes)
        size_info = f" ({width}x{height})" if width and height else ""
        await update.message.reply_text(
            f"📸 Фото сохранено{size_info}!\n"
            f"✏️ Используй /bg <описание> для замены фона"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def bg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not AGNES_API_KEY:
        await update.message.reply_text("❌ Agnes AI не настроен. Нет AGNES_API_KEY")
        return

    if 'last_image' not in context.user_data:
        await update.message.reply_text(
            "📸 Сначала загрузите картинку!\n"
            "Отправьте фото или сделайте скриншот /screen"
        )
        return

    if not context.args:
        await update.message.reply_text(
            "✏️ Напишите описание нового фона.\n"
            "Пример: /bg beach \n"
            "Пример: /bg космос"
        )
        return

    prompt = ' '.join(context.args)
    waiting_msg = await update.message.reply_text(
        f"🎨 Заменяю фон: {prompt}\n⏳ Ожидайте..."
    )

    try:
        image_data = context.user_data['last_image']
        loop = asyncio.get_event_loop()
        result_url, error = await loop.run_in_executor(
            None, replace_background, image_data, prompt
        )

        try:
            await waiting_msg.delete()
        except:
            pass

        if error:
            await update.message.reply_text(f"❌ Ошибка: {error}")
            return

        if result_url:
            try:
                if result_url.startswith('data:image'):
                    img_data = base64.b64decode(result_url.split(',')[1])
                    await update.message.reply_photo(
                        img_data,
                        caption=f"🖼️ Готово! Фон заменён на: {prompt}"
                    )
                else:
                    response = httpx.get(result_url, timeout=30)
                    if response.status_code == 200:
                        await update.message.reply_photo(
                            response.content,
                            caption=f"🖼️ Готово! Фон заменён на: {prompt}"
                        )
                    else:
                        await update.message.reply_text(f"❌ Ошибка загрузки: {response.status_code}")
            except Exception as e:
                logger.error(f"Ошибка скачивания: {e}")
                await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        else:
            await update.message.reply_text("❌ Не удалось заменить фон")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("run", run_command))
    app.add_handler(CommandHandler("tweets", tweets_command))
    app.add_handler(CommandHandler("log", log))
    app.add_handler(CommandHandler("skills", skills))
    app.add_handler(CommandHandler("memory", memory_command))
    app.add_handler(CommandHandler("image", image))
    app.add_handler(CommandHandler("images", images))
    
    app.add_handler(CommandHandler("bg", bg_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_terminal_input))

    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()