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
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from promt import SYSTEM_PROMPT
from PIL import Image

# DSPy импорты
import dspy
from dspy import ChainOfThought, Module, InputField, OutputField, Signature, settings

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
logging.getLogger("litellm").setLevel(logging.WARNING)

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
# DSPy ИНТЕГРАЦИЯ - ИСПРАВЛЕННЫЙ LM
# ============================================================

class AgnesLM(dspy.LM):
    """Адаптер для Agnes AI - с полной обработкой ошибок и параметров"""
    
    def __init__(self, model="agnes-2.0-flash", api_key=None, **kwargs):
        self.api_key = api_key or os.environ.get("AGNES_API_KEY")
        self.model = model
        self.kwargs = kwargs or {}
        self.provider = "agnes-ai"
        self.model_type = "chat"
        self.forward_contract = "legacy"
        self.cache = False
    
    def _call_agnes(self, messages, **kwargs):
        """Непосредственный вызов Agnes API с обработкой ошибок"""
        if not self.api_key:
            logger.error("❌ AGNES_API_KEY не задан")
            return ["Ошибка: API ключ не задан"]
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Объединяем параметры с приоритетом у kwargs
            params = {**self.kwargs, **kwargs}
            
            # Безопасное извлечение параметров с значениями по умолчанию
            temperature = params.get("temperature", 0.3)
            max_tokens = params.get("max_tokens", 2000)
            
            # Проверяем, что temperature - число
            if not isinstance(temperature, (int, float)):
                temperature = 0.3
            if not isinstance(max_tokens, (int, float)):
                max_tokens = 2000
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": float(temperature),
                "max_tokens": int(max_tokens)
            }
            
            logger.debug(f"📤 Запрос к Agnes: {payload['model']}, temp={temperature}, messages={len(messages)}")
            
            with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                response = client.post(
                    "https://apihub.agnes-ai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                
                # Проверяем структуру ответа
                if "choices" in data and len(data["choices"]) > 0:
                    choice = data["choices"][0]
                    if "message" in choice and "content" in choice["message"]:
                        result = choice["message"]["content"]
                        logger.debug(f"📥 Ответ от Agnes: {result[:100]}...")
                        return [result]
                    elif "text" in choice:
                        result = choice["text"]
                        logger.debug(f"📥 Ответ от Agnes: {result[:100]}...")
                        return [result]
                
                # Если структура неожиданная
                logger.error(f"❌ Неожиданный ответ от Agnes: {data}")
                return ["Ошибка: неожиданный формат ответа от API"]
                
        except httpx.TimeoutException:
            logger.error("❌ Таймаут запроса к Agnes API")
            return ["Ошибка: таймаут запроса к Agnes API (60 секунд)"]
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP ошибка: {e.response.status_code}")
            try:
                error_text = e.response.text[:200]
            except:
                error_text = "Нет данных"
            return [f"Ошибка HTTP {e.response.status_code}: {error_text}"]
        except httpx.RequestError as e:
            logger.error(f"❌ Ошибка запроса: {e}")
            return [f"Ошибка сети: {str(e)[:100]}"]
        except Exception as e:
            logger.error(f"❌ Неизвестная ошибка: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return [f"Ошибка: {str(e)[:200]}"]
    
    def __call__(self, prompt=None, messages=None, **kwargs):
        """Основной метод для вызова LM. Возвращает list[str]"""
        try:
            # Обрабатываем оба варианта - prompt и messages
            if messages:
                api_messages = messages
            else:
                api_messages = [{"role": "user", "content": prompt or ""}]
            
            # Передаем все kwargs дальше
            return self._call_agnes(api_messages, **kwargs)
        except Exception as e:
            logger.error(f"❌ Ошибка в __call__: {e}")
            return [f"Ошибка: {str(e)[:200]}"]
    
    def forward(self, prompt=None, messages=None, **kwargs):
        """Метод forward для DSPy"""
        return self.__call__(prompt=prompt, messages=messages, **kwargs)
    
    async def aforward(self, prompt=None, messages=None, **kwargs):
        """Асинхронная версия forward"""
        return self.__call__(prompt=prompt, messages=messages, **kwargs)

# Сигнатуры
class BrowserTask(Signature):
    task = InputField(desc="Задача пользователя")
    context = InputField(desc="Контекст страницы")
    code = OutputField(desc="Код на Python")
    explanation = OutputField(desc="Объяснение")

class ImageEnhanceTask(Signature):
    prompt = InputField(desc="Описание фона")
    image_info = InputField(desc="Информация об изображении")
    enhanced_prompt = OutputField(desc="Улучшенный промпт")
    style = OutputField(desc="Стиль")

class AnalysisTask(Signature):
    query = InputField(desc="Что нужно найти")
    content = InputField(desc="Содержимое страницы")
    answer = OutputField(desc="Ответ")
    confidence = OutputField(desc="Уверенность (0-1)")

# Модули с обработкой ошибок
class BrowserAgent(Module):
    def __init__(self):
        super().__init__()
        self.generate_code = ChainOfThought(BrowserTask)
    
    def forward(self, task, context=""):
        try:
            return self.generate_code(task=task, context=context)
        except Exception as e:
            logger.error(f"❌ BrowserAgent ошибка: {e}")
            # Возвращаем объект с полями по умолчанию
            class Result:
                code = f"# Ошибка: {str(e)[:200]}\nprint('Ошибка генерации кода')"
                explanation = f"Ошибка при генерации: {str(e)[:200]}"
            return Result()

class ImageEnhancer(Module):
    def __init__(self):
        super().__init__()
        self.enhance = ChainOfThought(ImageEnhanceTask)
    
    def forward(self, prompt, image_info=""):
        try:
            return self.enhance(prompt=prompt, image_info=image_info)
        except Exception as e:
            logger.error(f"❌ ImageEnhancer ошибка: {e}")
            class Result:
                enhanced_prompt = prompt
                style = "realistic"
            return Result()

class PageAnalyzer(Module):
    def __init__(self):
        super().__init__()
        self.analyze = ChainOfThought(AnalysisTask)
    
    def forward(self, query, content):
        try:
            return self.analyze(query=query, content=content)
        except Exception as e:
            logger.error(f"❌ PageAnalyzer ошибка: {e}")
            class Result:
                answer = f"Ошибка анализа: {str(e)[:200]}"
                confidence = "0.0"
            return Result()

# ============================================================
# ИНИЦИАЛИЗАЦИЯ DSPy
# ============================================================

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# Настройка DSPy
if AGNES_API_KEY:
    try:
        lm = AgnesLM(api_key=AGNES_API_KEY)
        settings.configure(lm=lm)
        logger.info("✅ DSPy настроен с AgnesLM")
        
        browser_agent = BrowserAgent()
        image_enhancer = ImageEnhancer()
        page_analyzer = PageAnalyzer()
        logger.info("✅ DSPy модули инициализированы")
        
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации DSPy: {e}")
        import traceback
        logger.error(traceback.format_exc())
        browser_agent = None
        image_enhancer = None
        page_analyzer = None
else:
    logger.warning("⚠️ AGNES_API_KEY не задан, DSPy не инициализирован")
    browser_agent = None
    image_enhancer = None
    page_analyzer = None

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
# НАСТРОЙКА БРАУЗЕРА
# ============================================================

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

os.environ["BU_CDP_URL"] = "http://localhost:9222"
try:
    ensure_daemon()
    logger.info("✅ Браузер готов")
except Exception as e:
    logger.error(f"❌ Ошибка запуска браузера: {e}")
    sys.exit(1)

set_cookies_global()
set_viewport_global()

# ============================================================
# GITHUB
# ============================================================

def push_to_github(content, filename, host="x.com"):
    """Отправить файл навыка в GitHub."""
    if not GITHUB_TOKEN:
        logger.warning("⚠️ GITHUB_TOKEN не задан")
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
    """Отправить agent_helpers.py в GitHub"""
    if not GITHUB_TOKEN:
        logger.warning("⚠️ GITHUB_TOKEN не задан")
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
# ФОТОШОП (AGNES AI)
# ============================================================

AGNES_IMAGE_API_URL = "https://apihub.agnes-ai.com/v1/images/generations"

def get_image_size(image_data):
    """Определяет размер изображения"""
    try:
        img = Image.open(io.BytesIO(image_data))
        width, height = img.size
        logger.info(f"📐 Размер изображения: {width}x{height}")
        return width, height
    except Exception as e:
        logger.error(f"Ошибка при определении размера: {e}")
        return None, None

def replace_background(image_data, new_background_prompt: str):
    """Заменяет фон изображения через Agnes AI."""
    if not AGNES_API_KEY:
        return None, "AGNES_API_KEY не установлен!"
    
    if not image_data:
        return None, "Нет данных изображения"
    
    if not new_background_prompt or len(new_background_prompt.strip()) < 2:
        return None, "Слишком короткое описание фона"
    
    try:
        enhanced_prompt_text = new_background_prompt
        if image_enhancer:
            try:
                width, height = get_image_size(image_data)
                image_info = f"Размер: {width}x{height}" if width and height else "Неизвестный размер"
                
                result = image_enhancer(prompt=new_background_prompt, image_info=image_info)
                if hasattr(result, 'enhanced_prompt') and result.enhanced_prompt:
                    enhanced_prompt_text = result.enhanced_prompt
                    logger.info(f"✨ DSPy улучшил промпт: {enhanced_prompt_text[:50]}...")
            except Exception as e:
                logger.warning(f"⚠️ DSPy улучшение промпта не удалось: {e}")
        
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
        Replace the background with: {enhanced_prompt_text}.
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

# ============================================================
# LLM (с поддержкой DSPy)
# ============================================================

async def ask_agnes_dspy(messages):
    """Использует DSPy для обработки запросов"""
    if not browser_agent:
        return await ask_agnes_fallback(messages)
    
    try:
        user_query = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_query = msg.get("content", "")
        
        if not user_query:
            return "❌ Нет запроса для обработки"
        
        try:
            page_info_data = page_info()
            context = f"URL: {page_info_data.get('url', 'unknown')}, Title: {page_info_data.get('title', 'unknown')}"
        except:
            context = "Нет активной страницы"
        
        logger.info(f"🧠 DSPy обрабатывает: {user_query}")
        
        result = browser_agent(task=user_query, context=context)
        
        # Извлекаем результат с проверкой
        if result is None:
            logger.warning("⚠️ DSPy вернул None")
            return await ask_agnes_fallback(messages)
        
        if hasattr(result, 'code'):
            code = result.code
            explanation = getattr(result, 'explanation', '')
        elif hasattr(result, 'completion'):
            code = result.completion
            explanation = ""
        elif hasattr(result, 'answer'):
            code = result.answer
            explanation = ""
        elif isinstance(result, dict):
            code = result.get('code', result.get('answer', str(result)))
            explanation = result.get('explanation', '')
        else:
            code = str(result)
            explanation = ""
        
        # Проверяем, что код не пустой
        if not code or code.strip() == "":
            logger.warning("⚠️ DSPy вернул пустой код")
            return await ask_agnes_fallback(messages)
        
        if "```python" not in code:
            response = f"```python\n{code}\n```\n\n💡 {explanation}"
        else:
            response = code
        
        logger.info(f"✅ DSPy сгенерировал ответ")
        return response
            
    except Exception as e:
        logger.error(f"❌ DSPy ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return await ask_agnes_fallback(messages)

async def ask_agnes_fallback(messages):
    """Обычный запрос к Agnes AI (без DSPy)"""
    logger.info("=" * 60)
    logger.info("📤 ОТПРАВКА В AGNES AI (FALLBACK):")
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

# ============================================================
# ВЫПОЛНИТЕЛЬ
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
# КОМАНДЫ
# ============================================================

async def start(update, context):
    await update.message.reply_text(
        "🌐 Браузер:\n"
        "/ask <запрос> — задать задачу агенту\n"
        "/image — последний скриншот\n"
        "/images — все скриншоты\n"
        "/skills — список навыков\n"
        "/log — скачать логи\n\n"
        "🎨 Фотошоп:\n"
        "/bg <описание> — заменить фон\n"
        "/clear — очистить кэш\n\n"
        "🧠 DSPy:\n"
        "/dspy <запрос> — использовать DSPy\n"
        "/analyze <вопрос> — анализ страницы"
    )

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

        if browser_agent:
            response = await ask_agnes_dspy(messages)
        else:
            response = await ask_agnes_fallback(messages)

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

# ============================================================
# DSPy КОМАНДЫ
# ============================================================

async def dspy_command(update, context):
    """Использовать DSPy напрямую"""
    if not browser_agent:
        await update.message.reply_text("❌ DSPy не инициализирован. Проверьте AGNES_API_KEY")
        return
    
    if not context.args:
        await update.message.reply_text("Пример: /dspy открыть google.com и сделать скриншот")
        return
    
    query = " ".join(context.args)
    username = update.effective_user.username or "unknown"
    logger.info(f"🧠 {username} DSPy запрос: {query}")
    
    status_msg = await update.message.reply_text("🧠 DSPy думает...")
    
    try:
        try:
            page_info_data = page_info()
            context_str = f"URL: {page_info_data.get('url', 'unknown')}, Title: {page_info_data.get('title', 'unknown')}"
        except:
            context_str = "Нет активной страницы"
        
        result = browser_agent(task=query, context=context_str)
        
        if result is None or not hasattr(result, 'code'):
            await status_msg.edit_text("❌ DSPy вернул пустой результат")
            return
        
        response = f"📝 **Код:**\n```python\n{result.code}\n```\n\n💡 **Объяснение:**\n{result.explanation}"
        await status_msg.edit_text(response, parse_mode='Markdown')
        
        if hasattr(result, 'code') and result.code:
            await update.message.reply_text("⚙️ Выполняю код...")
            output, success = execute_code(result.code)
            if success:
                await update.message.reply_text(f"✅ Результат:\n{output[:1000]}")
            else:
                await update.message.reply_text(f"❌ Ошибка выполнения:\n{output}")
                
    except Exception as e:
        logger.error(f"❌ DSPy ошибка: {e}")
        await status_msg.edit_text(f"❌ Ошибка DSPy: {str(e)[:200]}")

async def analyze_command(update, context):
    """Анализ содержимого страницы через DSPy"""
    if not page_analyzer:
        await update.message.reply_text("❌ DSPy не инициализирован")
        return
    
    if not context.args:
        await update.message.reply_text("Пример: /analyze какой сегодня курс доллара?")
        return
    
    query = " ".join(context.args)
    username = update.effective_user.username or "unknown"
    logger.info(f"🔍 {username} анализирует: {query}")
    
    status_msg = await update.message.reply_text("🔍 Анализирую страницу...")
    
    try:
        try:
            content = js("() => document.body.innerText.slice(0, 5000)")
            if not content:
                content = "Не удалось получить содержимое страницы"
        except:
            content = "Ошибка получения содержимого"
        
        result = page_analyzer(query=query, content=content)
        
        if result is None:
            await status_msg.edit_text("❌ Анализ не дал результата")
            return
        
        answer = getattr(result, 'answer', 'Нет ответа')
        confidence = getattr(result, 'confidence', '0.0')
        
        response = f"📊 **Ответ:**\n{answer}\n\n🎯 **Уверенность:** {confidence}"
        await status_msg.edit_text(response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"❌ Ошибка анализа: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# ФОТОШОП КОМАНДЫ
# ============================================================

async def clear_command(update, context):
    if 'last_image' in context.user_data:
        del context.user_data['last_image']
        await update.message.reply_text("🧹 Кэш очищен!")
    else:
        await update.message.reply_text("📭 Кэш пуст")

async def handle_photo(update, context):
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

async def bg_command(update, context):
    if not AGNES_API_KEY:
        await update.message.reply_text("❌ Agnes AI не настроен. Нет AGNES_API_KEY")
        return

    if 'last_image' not in context.user_data:
        await update.message.reply_text("📸 Сначала загрузите картинку!")
        return

    if not context.args:
        await update.message.reply_text("✏️ Напишите описание нового фона. Пример: /bg beach")
        return

    prompt = ' '.join(context.args)
    waiting_msg = await update.message.reply_text(f"🎨 Заменяю фон: {prompt}\n⏳ Ожидайте...")

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

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("log", log))
    app.add_handler(CommandHandler("skills", skills))
    app.add_handler(CommandHandler("image", image))
    app.add_handler(CommandHandler("images", images))
    
    app.add_handler(CommandHandler("dspy", dspy_command))
    app.add_handler(CommandHandler("analyze", analyze_command))
    
    app.add_handler(CommandHandler("bg", bg_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    logger.info("🚀 Бот запущен!")
    logger.info(f"🧠 DSPy статус: {'✅ Активен' if browser_agent else '❌ Отключен'}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()