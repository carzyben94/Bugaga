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

def get_harness_instruction() -> str:
    if not BROWSER_HARNESS:
        return ""
    
    domains = BROWSER_HARNESS.get("domains", [])
    total_methods = BROWSER_HARNESS.get("total_methods", 0)
    
    domain_examples = []
    for domain in domains[:5]:
        domain_name = domain.get("domain", "unknown")
        methods = [m.get("name") for m in domain.get("methods", [])[:3]]
        domain_examples.append(f"  • {domain_name}: {', '.join(methods)}...")
    
    return f"""
=== ВСЕ 652 МЕТОДА CDP ДОСТУПНЫ ===
У тебя есть доступ ко всем {total_methods} методам CDP через 56 доменов.

Основные домены:
{chr(10).join(domain_examples)}

Ты можешь использовать ЛЮБОЙ CDP-метод напрямую.
"""

async def get_response(user_msg: str, error_context: str = None) -> str:
    if not AGNES_API_KEY:
        return "❌ AGNES_API_KEY не задан"
    if error_context:
        set_last_error(error_context)
    add_to_memory("user", user_msg)

    harness_instruction = get_harness_instruction()

    system_prompt = f"""Ты агент, управляющий браузером через CDP.

Твоя задача — создавать xBRIEF планы для выполнения любых действий в браузере.

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
      {{"id": "step1", "title": "Page.navigate", "params": {{"url": "..."}}}},
      {{"id": "step2", "title": "Runtime.evaluate", "params": {{"expression": "..."}}}},
      {{"id": "step3", "title": "Page.captureScreenshot", "params": {{"format": "png"}}}}
    ],
    "edges": [
      {{"from": "step1", "to": "step2", "type": "blocks"}},
      {{"from": "step2", "to": "step3", "type": "blocks"}}
    ],
    "narratives": {{
      "Outcome": "Что получилось",
      "Lessons": "Что узнали"
    }}
  }}
}}

=== ОСНОВНЫЕ CDP-КОМАНДЫ ===

1. Page.navigate — открыть URL
   params: {{"url": "https://example.com"}}

2. Page.captureScreenshot — скриншот
   params: {{"format": "png", "captureBeyondViewport": false}}

3. Runtime.evaluate — выполнить JavaScript
   params: {{"expression": "код"}}

4. Input.dispatchMouseEvent — клик по координатам
   params: {{"type": "mousePressed", "x": 100, "y": 200, "button": "left"}}

5. Input.insertText — ввести текст
   params: {{"text": "hello"}}

6. Network.setCookie — установить куку
   params: {{"name": "session", "value": "123", "url": "https://example.com"}}

7. Emulation.setDeviceMetricsOverride — эмуляция устройства
   params: {{"width": 375, "height": 812, "mobile": true, "deviceScaleFactor": 3}}

8. DOM.getDocument — получить DOM
9. DOM.querySelector — найти элемент
10. DOM.querySelectorAll — найти все элементы

=== КАК ИСКАТЬ ЭЛЕМЕНТЫ ===

// ССЫЛКИ
document.querySelectorAll('a[href]') → {{text, href}}
document.querySelectorAll('[role="link"]')

// КНОПКИ
document.querySelectorAll('button, [role="button"], input[type="submit"]') → {{text, type, id}}

// ПОЛЯ
document.querySelectorAll('input:not([type="hidden"]), textarea, [contenteditable="true"]') → {{name, type, placeholder}}

// ИЗОБРАЖЕНИЯ
document.querySelectorAll('img[src]') → {{src, alt, width, height}}

// ЗАГОЛОВКИ
document.querySelectorAll('h1, h2, h3, h4') → {{tag, text}}

// ТВИТЫ (X.com)
document.querySelectorAll('[data-testid="tweet"], article[data-testid="tweet"]') → {{text, author, likes, retweets}}

// ТРЕНДЫ (X.com)
document.querySelectorAll('[data-testid="trend"]') → {{name, tweets}}

// ВСЕ DATA-TESTID (X.com)
document.querySelectorAll('[data-testid]') → список

// ТЕКСТ
document.body.innerText

// ВСЯ СТРУКТУРА
document.body.innerHTML

=== ПРОВЕРКА ВИДИМОСТИ ===
// Проверить, виден ли элемент
el.offsetParent !== null
el.getBoundingClientRect().width > 0
window.getComputedStyle(el).display !== 'none'
window.getComputedStyle(el).visibility !== 'hidden'

// Найти только видимые элементы
Array.from(document.querySelectorAll('button')).filter(el => el.offsetParent !== null)

=== IFRAME ===
document.querySelectorAll('iframe')

=== LOCALSTORAGE ===
localStorage.getItem('key')
localStorage.setItem('key', 'value')
localStorage.removeItem('key')
Object.keys(localStorage)

=== FETCH ===
fetch('https://api.example.com/data').then(r => r.json())
fetch('https://api.example.com/data', {{
  method: 'POST',
  headers: {{'Content-Type': 'application/json'}},
  body: JSON.stringify({{key: 'value'}})
}})

=== ОБРАБОТКА ОШИБОК ===
Если команда не сработала:
1. Проверь, что страница загружена → document.readyState === 'complete'
2. Попробуй другой селектор
3. Добавь задержку → await new Promise(r => setTimeout(r, 2000))
4. Если ничего не помогает → верни {{"error": "..."}}

=== ОЖИДАНИЕ ЭЛЕМЕНТОВ ===
// Ждать появления элемента
await new Promise(r => {{
  const check = () => {{
    if (document.querySelector('selector')) r();
    else setTimeout(check, 100);
  }};
  check();
}})

// Ждать с таймаутом
await new Promise((r, reject) => {{
  const start = Date.now();
  const check = () => {{
    if (document.querySelector('selector')) r();
    else if (Date.now() - start > 10000) reject('Timeout');
    else setTimeout(check, 100);
  }};
  check();
}})

=== СКРОЛЛ ===
// Скролл вниз
window.scrollBy(0, 1000)

// Скролл до элемента
document.querySelector('selector').scrollIntoView()

// Плавный скролл
window.scrollTo({{top: 1000, behavior: 'smooth'}})

=== АТРИБУТЫ И КЛАССЫ ===
// Получить атрибут
el.getAttribute('href')
el.getAttribute('data-testid')

// Проверить класс
el.classList.contains('active')

// Получить все классы
Array.from(el.classList)

=== ФОРМЫ И СОБЫТИЯ ===
// Найти форму
document.querySelectorAll('form')

// Отправить форму
form.submit()

// Вызвать событие
el.dispatchEvent(new Event('click', {{bubbles: true}}))
el.dispatchEvent(new Event('change', {{bubbles: true}}))
el.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter'}}))

=== ПРИМЕРЫ ПЛАНОВ ===

ПРИМЕР 1: Открыть сайт и скриншот
{{
  "items": [
    {{"title": "Page.navigate", "params": {{"url": "https://google.com"}}}},
    {{"title": "Page.captureScreenshot", "params": {{"format": "png"}}}}
  ],
  "edges": [{{"from": "step1", "to": "step2"}}]
}}

ПРИМЕР 2: Поиск в Google
{{
  "items": [
    {{"title": "Page.navigate", "params": {{"url": "https://www.google.com"}}}},
    {{"title": "Runtime.evaluate", "params": {{"expression": "document.querySelector('textarea[name=\"q\"]').value = 'погода'; document.querySelector('input[name=\"btnK\"]')?.click()"}}}},
    {{"title": "Page.captureScreenshot", "params": {{"format": "png"}}}}
  ],
  "edges": [{{"from": "step1", "to": "step2"}}, {{"from": "step2", "to": "step3"}}]
}}

ПРИМЕР 3: Извлечение твитов (С ПРОВЕРКОЙ РЕЗУЛЬТАТА)
{{
  "items": [
    {{"title": "Page.navigate", "params": {{"url": "https://x.com/elonmusk"}}}},
    {{"title": "Runtime.evaluate", "params": {{"expression": "await new Promise(r => setTimeout(r, 3000)); const tweets = Array.from(document.querySelectorAll('[data-testid=\"tweet\"]')); if (tweets.length === 0) return {{ error: 'Твиты не найдены' }}; return tweets.slice(0,5).map(t => ({{ text: t.querySelector('[data-testid=\"tweetText\"]')?.innerText || '', author: t.querySelector('[data-testid=\"User-Name\"] span')?.innerText || '', likes: t.querySelector('[data-testid=\"like\"] span')?.innerText || '0' }}))"}}}}
  ],
  "edges": [{{"from": "step1", "to": "step2"}}],
  "narratives": {{
    "Outcome": "Найдено твитов: {{count}}"
  }}
}}

ПРИМЕР 4: Эмуляция iPhone
{{
  "items": [
    {{"title": "Emulation.setDeviceMetricsOverride", "params": {{"width": 375, "height": 812, "deviceScaleFactor": 3, "mobile": true}}}},
    {{"title": "Page.navigate", "params": {{"url": "https://example.com"}}}},
    {{"title": "Page.captureScreenshot", "params": {{"format": "png"}}}}
  ],
  "edges": [{{"from": "step1", "to": "step2"}}, {{"from": "step2", "to": "step3"}}]
}}

{harness_instruction}

=== ЖЁСТКИЕ ПРАВИЛА ===
1. ВСЕГДА возвращай ТОЛЬКО ПОЛНЫЙ валидный JSON с xBRIEF планом
2. НИКОГДА не пиши пояснения, только JSON
3. Убедись, что все скобки и кавычки закрыты
4. Каждый шаг — это одна CDP-команда
5. Используй edges для указания порядка шагов
6. После выполнения плана заполни narratives.Outcome на основе РЕАЛЬНЫХ данных
7. Для X.com используй document.querySelectorAll('[data-testid]') для поиска селекторов
8. Для ожидания загрузки добавь: await new Promise(r => setTimeout(r, 3000))
9. ✅ ОБЯЗАТЕЛЬНО проверяй результат! Если элементов нет → верни {"error": "Не найдено"}
10. ✅ НЕ говори "успешно", если данных нет
11. ✅ Всегда проверяй видимость элементов перед взаимодействием
12. ✅ В narratives.Outcome пиши ТОЛЬКО реальный результат (количество найденных элементов)
"""
    messages = [{"role": "system", "content": system_prompt}] + get_memory_history()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                AGNES_API_URL,
                json={"model": AI_MODEL, "messages": messages, "temperature": 0.2, "max_tokens": 800},
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
            
            json_str = response[start:end].strip()
            
            open_braces = json_str.count('{')
            close_braces = json_str.count('}')
            
            if open_braces > close_braces:
                json_str += '}' * (open_braces - close_braces)
            
            if json_str.count('"') % 2 != 0:
                json_str += '"'
            
            data = json.loads(json_str)
            
            if "xBRIEFInfo" in data and "plan" in data:
                return {"type": "xbrief", "data": data}
            elif "method" in data:
                return {"type": "command", "data": data}
    except Exception as e:
        add_log("parse_error", str(e), "error")
        add_log("parse_debug", response[:300], "info")
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
    
    if BROWSER_HARNESS:
        stats["browser_harness"]["loaded"] = True
        stats["browser_harness"]["total_methods"] = BROWSER_HARNESS.get("total_methods", 0)
        stats["browser_harness"]["total_domains"] = BROWSER_HARNESS.get("total_domains", 0)
    
    return stats