import os
import json
import httpx
import base64
import time
from typing import Dict, Optional, List
from datetime import datetime

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
MEMORY_PATH = "memory.json"
LOGS_PATH = "logs.json"

_last_github_save = 0
GITHUB_SAVE_INTERVAL = 80
_pending_memory_data = None
_pending_logs_data = None

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
    global _last_github_save, _pending_memory_data, _pending_logs_data
    if path == MEMORY_PATH:
        _pending_memory_data = (data, sha)
    elif path == LOGS_PATH:
        _pending_logs_data = (data, sha)
    current_time = time.time()
    if not force and (current_time - _last_github_save) < GITHUB_SAVE_INTERVAL:
        print(f"⏳ Отложено {path} ({GITHUB_SAVE_INTERVAL}с)")
        return sha
    return _save_to_github_immediate(path, data, sha)

def _save_to_github_immediate(path: str, data, sha: Optional[str] = None):
    global _last_github_save
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
            _last_github_save = time.time()
            print(f"💾 Сохранено: {path}")
            return resp.json().get("content", {}).get("sha")
        print(f"⚠️ Ошибка {path}: {resp.status_code}")
        return sha
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")
        return sha

def flush_pending_saves():
    global _last_github_save, _pending_memory_data, _pending_logs_data
    _last_github_save = 0
    if _pending_memory_data:
        data, sha = _pending_memory_data
        save_to_github(MEMORY_PATH, data, sha, force=True)
        _pending_memory_data = None
    if _pending_logs_data:
        data, sha = _pending_logs_data
        save_to_github(LOGS_PATH, data, sha, force=True)
        _pending_logs_data = None

def add_to_memory(role: str, content: str):
    global history, memory_sha
    history.append({"role": role, "content": content})
    if len(history) > 15:
        history.pop(0)
    data = {"history": history, "last_error": last_error, "updated_at": datetime.now().isoformat()}
    memory_sha = save_to_github(MEMORY_PATH, data, memory_sha)

def get_memory_history() -> List[Dict[str, str]]:
    return history

def clear_memory():
    global history, last_error, memory_sha
    history = []
    last_error = None
    data = {"history": history, "last_error": last_error, "updated_at": datetime.now().isoformat()}
    memory_sha = save_to_github(MEMORY_PATH, data, memory_sha, force=True)

def set_last_error(error: str):
    global last_error, memory_sha
    last_error = error
    data = {"history": history, "last_error": last_error, "updated_at": datetime.now().isoformat()}
    memory_sha = save_to_github(MEMORY_PATH, data, memory_sha)

def get_last_error() -> Optional[str]:
    return last_error

def add_log(action: str, details: str, status: str = "info"):
    global logs, logs_sha
    logs.append({"timestamp": datetime.now().isoformat(), "action": action, "details": details, "status": status})
    if len(logs) > 100:
        logs.pop(0)
    logs_sha = save_to_github(LOGS_PATH, logs, logs_sha)

def get_logs() -> List[Dict]:
    return logs

def clear_logs():
    global logs, logs_sha
    logs = []
    logs_sha = save_to_github(LOGS_PATH, logs, logs_sha, force=True)

def get_memory_stats() -> Dict:
    return {"history_count": len(history), "max_history": 15, "last_error": last_error}

load_from_github(MEMORY_PATH)
load_from_github(LOGS_PATH)
print("🚀 Агент загружен")

def load_protocols():
    try:
        with open(BROWSER_PROTOCOL, 'r') as f:
            add_log("protocols_loaded", "OK", "success")
            return json.load(f)
    except Exception as e:
        add_log("protocols_error", str(e), "error")
        return None

BROWSER_DOMAINS = load_protocols()

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

async def get_response(user_msg: str, error_context: str = None) -> str:
    if not AGNES_API_KEY:
        add_log("api_error", "AGNES_API_KEY не задан", "error")
        return "❌ AGNES_API_KEY не задан"
    if error_context:
        set_last_error(error_context)
    add_to_memory("user", user_msg)

    system_prompt = """Ты агент, управляющий браузером через CDP.

Если пользователь просит несколько действий (например, "открой и сделай скриншот"):
1. Сначала верни ПЕРВУЮ команду
2. В ответе напиши, что нужно сделать дальше

Доступные команды:
""" + get_all_commands() + """

Правила:
- Верни JSON: {"method": "Domain.command", "params": {...}}
- Если несколько действий — делай по очереди
- После каждой команды напоминай, что дальше
- Если команда не требуется — ответь текстом

Пример:
Пользователь: "открой google.com и сделай скриншот"
Твой ответ:
{"method": "Page.navigate", "params": {"url": "https://google.com"}}
✅ Страница открыта. Теперь сделаю скриншот.

Простые команды:
""" + get_common_commands()

    messages = [{"role": "system", "content": system_prompt}] + get_memory_history()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                AGNES_API_URL,
                json={"model": AI_MODEL, "messages": messages, "temperature": 0.2, "max_tokens": 500},
                headers={"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"},
                timeout=30.0
            )
            result = resp.json()["choices"][0]["message"]["content"]
            add_to_memory("assistant", result)
            add_log("ai_response", result[:100], "success")
            return result
    except Exception as e:
        add_log("api_error", str(e), "error")
        return f"❌ Ошибка API: {str(e)}"

def parse_command(response: str) -> Optional[Dict]:
    try:
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            response = response[start:end].strip()
        if "{" in response and "method" in response:
            start = response.find("{")
            end = response.rfind("}") + 1
            data = json.loads(response[start:end])
            if "method" in data:
                method = data.get("method")
                params = data.get("params", {})
                cmd_info = get_full_command_info(method)
                if cmd_info:
                    required = [p.get("name") for p in cmd_info.get("parameters", []) if p.get("optional") is not True]
                    missing = [p for p in required if p not in params]
                    if missing:
                        add_log("missing_params", f"{method}: {missing}", "error")
                        return None
                return data
    except Exception as e:
        add_log("parse_error", str(e), "error")
    return None