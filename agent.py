import os 
import json
import httpx
import base64
import time
from typing import Dict, Optional, List, Any
from datetime import datetime

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
MEMORY_PATH = "memory.json"
LOGS_PATH = "logs.json"

if GITHUB_TOKEN:
    print("🔑 GitHub токен найден")
    print(f"📁 Репозиторий: {GITHUB_REPO}")
    print(f"🌿 Ветка: {GITHUB_BRANCH}")
else:
    print("⚠️ GitHub токен НЕ задан")

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
AGNES_API_URL = os.environ.get("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")
AI_MODEL = os.environ.get("AI_MODEL", "agnes-2.0-flash")
PROTOCOLS_DIR = os.environ.get("PROTOCOLS_DIR", "/app/docs")
BROWSER_PROTOCOL = os.path.join(PROTOCOLS_DIR, "browser_protocol.json")
JS_PROTOCOL = os.path.join(PROTOCOLS_DIR, "js_protocol.json")
XBRIEF_SCHEMA_PATH = os.path.join(PROTOCOLS_DIR, "vbrief-core.schema.json")
BROWSER_LOGIC_PATH = os.path.join(PROTOCOLS_DIR, "browser-logic.json")
BROWSER_HARNESS_PATH = os.path.join(PROTOCOLS_DIR, "browser-harness-all.json")

history: List[Dict[str, str]] = []
last_error: Optional[str] = None
memory_sha: Optional[str] = None
logs_sha: Optional[str] = None
logs: List[Dict] = []

def load_from_github(path: str):
    global history, last_error, memory_sha, logs, logs_sha
    try:
        if not GITHUB_TOKEN or not GITHUB_REPO:
            return
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        resp = httpx.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            parsed = json.loads(content)
            if path == MEMORY_PATH:
                memory_sha = data["sha"]
                history = parsed.get("history", [])
                last_error = parsed.get("last_error")
                print(f"📂 Загружено {len(history)} сообщений")
            elif path == LOGS_PATH:
                logs_sha = data["sha"]
                logs = parsed
                print(f"📂 Загружено {len(logs)} логов")
    except Exception as e:
        print(f"⚠️ Ошибка загрузки {path}: {e}")

def save_to_github(path: str, data, sha: Optional[str] = None, force: bool = False):
    if not force:
        return sha
    return _save_to_github_immediate(path, data, sha)

def _save_to_github_immediate(path: str, data, sha: Optional[str] = None):
    try:
        if not GITHUB_TOKEN or not GITHUB_REPO:
            return sha
        content = base64.b64encode(json.dumps(data, indent=2).encode()).decode()
        payload = {"message": f"Update {path}", "content": content, "branch": GITHUB_BRANCH}
        if sha:
            payload["sha"] = sha
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        resp = httpx.put(url, json=payload, headers=headers) if sha else httpx.post(url, json=payload, headers=headers)
        if resp.status_code in [200, 201]:
            return resp.json().get("content", {}).get("sha")
        return sha
    except Exception as e:
        return sha

def flush_pending_saves():
    global history, memory_sha, logs, logs_sha
    if history:
        data = {"history": history, "last_error": last_error, "updated_at": datetime.now().isoformat()}
        memory_sha = save_to_github(MEMORY_PATH, data, memory_sha, force=True)
    if logs:
        logs_sha = save_to_github(LOGS_PATH, logs, logs_sha, force=True)

def add_to_memory(role: str, content: str):
    global history
    history.append({"role": role, "content": content})
    if len(history) > 15:
        history.pop(0)

def get_memory_history() -> List[Dict[str, str]]:
    return history

def clear_memory():
    global history, last_error
    history = []
    last_error = None

def set_last_error(error: str):
    global last_error
    last_error = error

def get_last_error() -> Optional[str]:
    return last_error

def add_log(action: str, details: str, status: str = "info"):
    global logs
    logs.append({"timestamp": datetime.now().isoformat(), "action": action, "details": details, "status": status})
    if len(logs) > 100:
        logs.pop(0)

def get_logs() -> List[Dict]:
    return logs

def clear_logs():
    global logs
    logs = []

def get_memory_stats() -> Dict:
    return {"history_count": len(history), "max_history": 15, "last_error": last_error}

load_from_github(MEMORY_PATH)
load_from_github(LOGS_PATH)
print("🚀 Агент загружен")

def load_xbrief_schema():
    try:
        with open(XBRIEF_SCHEMA_PATH, 'r', encoding='utf-8-sig') as f:
            schema = json.load(f)
            print("📄 xBRIEF Core v0.8 загружена")
            return schema
    except Exception as e:
        print(f"⚠️ Ошибка загрузки xBRIEF: {e}")
        return None

XBRIEF_SCHEMA = load_xbrief_schema()

def load_protocols():
    try:
        with open(BROWSER_PROTOCOL, 'r') as f:
            return json.load(f)
    except Exception as e:
        return None

def load_js_protocol():
    try:
        with open(JS_PROTOCOL, 'r') as f:
            return json.load(f)
    except Exception as e:
        return None

BROWSER_DOMAINS = load_protocols()
JS_DOMAINS = load_js_protocol()

if JS_DOMAINS:
    print(f"📂 Загружен js_protocol.json ({len(JS_DOMAINS.get('domains', []))} доменов)")

# ===== ЗАГРУЗКА ЛОГИКИ БРАУЗЕРА =====
def load_browser_logic():
    try:
        with open(BROWSER_LOGIC_PATH, 'r', encoding='utf-8-sig') as f:
            logic = json.load(f)
            print("📄 browser-logic.json загружен")
            return logic
    except Exception as e:
        print(f"⚠️ Ошибка загрузки browser-logic.json: {e}")
        return None

BROWSER_LOGIC = load_browser_logic()

# ===== ЗАГРУЗКА BROWER-HARNESS-ALL =====
def load_browser_harness():
    try:
        with open(BROWSER_HARNESS_PATH, 'r', encoding='utf-8-sig') as f:
            harness = json.load(f)
            print(f"📄 browser-harness-all.json загружен ({harness.get('total_methods', 0)} методов, {harness.get('total_domains', 0)} доменов)")
            return harness
    except Exception as e:
        print(f"⚠️ Ошибка загрузки browser-harness-all.json: {e}")
        return None

BROWSER_HARNESS = load_browser_harness()

def get_full_command_info(method: str) -> Optional[Dict]:
    if not BROWSER_DOMAINS:
        return None
    try:
        domain_name, cmd_name = method.split(".", 1)
        for domain in BROWSER_DOMAINS.get("domains", []):
            if domain.get("domain") == domain_name:
                for cmd in domain.get("commands", []):
                    if cmd.get("name") == cmd_name:
                        return cmd
    except:
        pass
    return None

def get_common_commands() -> str:
    return """
Page.navigate — открыть URL. Нужен параметр: url
Page.captureScreenshot — сделать скриншот. Параметры: format (png), captureBeyondViewport (false)
Runtime.evaluate — выполнить JS. Нужен параметр: expression
"""

def get_all_commands() -> str:
    if not BROWSER_DOMAINS:
        return "Протоколы не загружены"
    lines = []
    for domain in BROWSER_DOMAINS.get("domains", []):
        domain_name = domain.get("domain")
        for cmd in domain.get("commands", []):
            cmd_name = cmd.get("name")
            params = cmd.get("parameters", [])
            required = [p.get("name") for p in params if p.get("optional") is not True]
            desc = cmd.get("description", "")[:40]
            if required:
                lines.append(f"  {domain_name}.{cmd_name}({', '.join(required)}) — {desc}")
            else:
                lines.append(f"  {domain_name}.{cmd_name} — {desc}")
    return "\n".join(lines[:40])

def get_browser_harness_instruction() -> str:
    """Формирует инструкцию на основе browser-harness-all.json"""
    if not BROWSER_HARNESS:
        return ""
    
    domains = BROWSER_HARNESS.get("domains", [])
    rules = BROWSER_HARNESS.get("rules", [])
    total_methods = BROWSER_HARNESS.get("total_methods", 0)
    
    # Берём первые 5 доменов для примера (чтобы не перегружать промпт)
    domain_examples = []
    for domain in domains[:5]:
        domain_name = domain.get("domain", "unknown")
        methods = [m.get("name") for m in domain.get("methods", [])[:3]]
        domain_examples.append(f"  • {domain_name}: {', '.join(methods)}...")
    
    instruction = f"""
=== ПОЛНАЯ ЛОГИКА CDP (browser-harness-all.json) ===
У тебя есть доступ ко всем {total_methods} методам CDP через 56 доменов.

Примеры доменов и методов:
{chr(10).join(domain_examples)}

Основные правила:
{chr(10).join([f"- {r}" for r in rules[:8]])}

Ты можешь использовать ЛЮБОЙ CDP-метод напрямую. Если нужного метода нет в списке — ищи в browser-harness-all.json.
"""
    return instruction

async def get_response(user_msg: str, error_context: str = None) -> str:
    if not AGNES_API_KEY:
        return "❌ AGNES_API_KEY не задан"
    if error_context:
        set_last_error(error_context)
    add_to_memory("user", user_msg)

    # Формируем инструкцию по browser-logic.json
    browser_logic_instruction = ""
    if BROWSER_LOGIC:
        actions = BROWSER_LOGIC.get("actions", {})
        rules = BROWSER_LOGIC.get("rules", [])
        
        action_list = []
        for name, action in actions.items():
            action_list.append(f"- {name}: {action.get('description', '')}")
        
        browser_logic_instruction = f"""
=== ДОПОЛНИТЕЛЬНАЯ ЛОГИКА ДЛЯ БРАУЗЕРА (browser-logic.json) ===
Ты можешь использовать следующие действия:

{chr(10).join(action_list)}

Правила:
{chr(10).join([f"- {r}" for r in rules])}
"""

    # Формируем инструкцию по browser-harness-all.json
    harness_instruction = get_browser_harness_instruction()

    system_prompt = f"""Ты агент, управляющий браузером через CDP.

Твоя задача — создавать xBRIEF планы для выполнения действий в браузере.

=== СТРУКТУРА xBRIEF ПЛАНА ===
{{
  "xBRIEFInfo": {{
    "version": "0.8",
    "author": "agent",
    "created": "2026-07-17T00:00:00Z"
  }},
  "plan": {{
    "title": "Название плана",
    "status": "running",
    "items": [
      {{"id": "step1", "type": "task", "title": "Page.navigate", "status": "pending", "params": {{"url": "..."}}}},
      {{"id": "step2", "type": "task", "title": "Page.captureScreenshot", "status": "pending", "params": {{"format": "png"}}}}
    ],
    "edges": [
      {{"from": "step1", "to": "step2", "type": "blocks"}}
    ],
    "narratives": {{
      "Outcome": "Что получилось",
      "Lessons": "Что узнали"
    }}
  }}
}}

=== ДОСТУПНЫЕ CDP-КОМАНДЫ (из browser_protocol.json) ===
{get_all_commands()}

{browser_logic_instruction}

{harness_instruction}

=== ПРАВИЛА ===
1. ВСЕГДА возвращай ТОЛЬКО JSON с xBRIEF планом
2. НИКОГДА не пиши пояснения, только JSON
3. Каждый шаг — это одна CDP-команда
4. Используй edges для указания порядка шагов
5. После выполнения плана заполни narratives.Outcome
6. Для сложных задач используй методы из browser-harness-all.json

=== ПРИМЕР ===
Пользователь: "открой google.com и сделай скриншот"
Твой ответ:
{{
  "xBRIEFInfo": {{
    "version": "0.8",
    "author": "agent",
    "created": "2026-07-17T00:00:00Z"
  }},
  "plan": {{
    "title": "Открыть сайт и сделать скриншот",
    "status": "running",
    "items": [
      {{"id": "step1", "type": "task", "title": "Page.navigate", "status": "pending", "params": {{"url": "https://google.com"}}}},
      {{"id": "step2", "type": "task", "title": "Page.captureScreenshot", "status": "pending", "params": {{"format": "png", "captureBeyondViewport": false}}}}
    ],
    "edges": [
      {{"from": "step1", "to": "step2", "type": "blocks"}}
    ],
    "narratives": {{
      "Outcome": "Сайт открыт, скриншот сделан",
      "Lessons": "Цепочка выполняется автоматически"
    }}
  }}
}}
"""
    messages = [{"role": "system", "content": system_prompt}] + get_memory_history()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                AGNES_API_URL,
                json={"model": AI_MODEL, "messages": messages, "temperature": 0.2, "max_tokens": 600},
                headers={"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"},
                timeout=30.0
            )
            result = resp.json()["choices"][0]["message"]["content"]
            add_to_memory("assistant", result)
            return result
    except Exception as e:
        add_log("api_error", str(e), "error")
        return f"❌ Ошибка API: {str(e)}"

def parse_response(response: str) -> Optional[Dict]:
    try:
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            response = response[start:end].strip()
        if "{" in response:
            start = response.find("{")
            end = response.rfind("}") + 1
            data = json.loads(response[start:end])
            if "xBRIEFInfo" in data and "plan" in data:
                return {"type": "xbrief", "data": data}
            elif "method" in data:
                return {"type": "command", "data": data}
    except Exception as e:
        add_log("parse_error", str(e), "error")
    return None

def parse_command(response: str) -> Optional[Dict]:
    return parse_response(response)

def parse_xbrief_plan(response: str) -> Optional[Dict]:
    parsed = parse_response(response)
    if parsed and parsed.get("type") == "xbrief":
        return parsed["data"]
    return None

def parse_simple_command(response: str) -> Optional[Dict]:
    parsed = parse_response(response)
    if parsed and parsed.get("type") == "command":
        return parsed["data"]
    return None

def get_protocols_stats() -> Dict:
    stats = {
        "browser": {"loaded": False, "domains": 0, "commands": 0},
        "js": {"loaded": False, "domains": 0, "commands": 0},
        "xbrief": {"loaded": False},
        "browser_logic": {"loaded": False},
        "browser_harness": {"loaded": False, "total_methods": 0, "total_domains": 0}
    }
    
    if BROWSER_DOMAINS:
        stats["browser"]["loaded"] = True
        stats["browser"]["domains"] = len(BROWSER_DOMAINS.get("domains", []))
        for domain in BROWSER_DOMAINS.get("domains", []):
            stats["browser"]["commands"] += len(domain.get("commands", []))
    
    if JS_DOMAINS:
        stats["js"]["loaded"] = True
        stats["js"]["domains"] = len(JS_DOMAINS.get("domains", []))
        for domain in JS_DOMAINS.get("domains", []):
            stats["js"]["commands"] += len(domain.get("commands", []))
    
    if XBRIEF_SCHEMA:
        stats["xbrief"]["loaded"] = True
    
    if BROWSER_LOGIC:
        stats["browser_logic"]["loaded"] = True
    
    if BROWSER_HARNESS:
        stats["browser_harness"]["loaded"] = True
        stats["browser_harness"]["total_methods"] = BROWSER_HARNESS.get("total_methods", 0)
        stats["browser_harness"]["total_domains"] = BROWSER_HARNESS.get("total_domains", 0)
    
    return stats