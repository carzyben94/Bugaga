import os
import json
import httpx
from typing import Dict, Optional, List

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
AGNES_API_URL = os.environ.get("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")
AI_MODEL = os.environ.get("AI_MODEL", "agnes-2.0-flash")
PROTOCOLS_DIR = os.environ.get("PROTOCOLS_DIR", "/app/docs")
BROWSER_PROTOCOL = os.path.join(PROTOCOLS_DIR, "browser_protocol.json")

class AgentMemory:
    def __init__(self, max_history: int = 15):
        self.history: List[Dict[str, str]] = []
        self.max_history = max_history
        self.last_error: Optional[str] = None
    
    def add(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
        if len(self.history) > self.max_history:
            self.history.pop(0)
    
    def get_messages(self) -> List[Dict[str, str]]:
        return self.history
    
    def set_error(self, error: str):
        self.last_error = error
        self.add("system", f"Ошибка CDP: {error}")
    
    def clear(self):
        self.history = []
        self.last_error = None

memory = AgentMemory()

def load_protocols():
    try:
        with open(BROWSER_PROTOCOL, 'r') as f:
            return json.load(f)
    except:
        return None

BROWSER_DOMAINS = load_protocols()

def get_full_command_info(method: str) -> Optional[Dict]:
    """Возвращает полную информацию о команде из протокола"""
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

def get_command_params(method: str) -> Dict:
    """Возвращает параметры команды с типами и описанием"""
    cmd_info = get_full_command_info(method)
    if not cmd_info:
        return {}
    
    params = {}
    for p in cmd_info.get("parameters", []):
        name = p.get("name")
        p_type = p.get("type", "string")
        optional = p.get("optional", False)
        description = p.get("description", "")[:60]
        params[name] = {
            "type": p_type,
            "optional": optional,
            "description": description
        }
    return params

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

def get_common_commands() -> str:
    """Часто используемые команды с примерами"""
    return """
Page.navigate — открыть URL. Нужен параметр: url
Page.captureScreenshot — сделать скриншот. Параметры: format (png), captureBeyondViewport (false)
Runtime.evaluate — выполнить JS. Нужен параметр: expression
Input.dispatchMouseEvent — кликнуть. Нужны: type (mousePressed/mouseReleased), x, y
"""

async def get_response(user_msg: str, error_context: str = None) -> str:
    if not AGNES_API_KEY:
        return "❌ AGNES_API_KEY не задан"
    
    # Если есть ошибка — добавляем в память
    if error_context:
        memory.set_error(error_context)
    
    memory.add("user", user_msg)
    
    system_prompt = f"""Ты агент, управляющий браузером через CDP.

Доступные команды:
{get_all_commands()}

Простые команды (рекомендую):
{get_common_commands()}

Правила:
1. Верни JSON: {{"method": "Domain.command", "params": {{...}}}}
2. В params указывай ВСЕ обязательные параметры
3. Если была ошибка — проанализируй её и исправь команду
4. Используй простые команды, если не уверен

Примеры:
- Открыть сайт: {{"method": "Page.navigate", "params": {{"url": "https://google.com"}}}}
- Скриншот: {{"method": "Page.captureScreenshot", "params": {{"format": "png", "captureBeyondViewport": false}}}}
- Заголовок: {{"method": "Runtime.evaluate", "params": {{"expression": "document.title"}}}}
- Клик: {{"method": "Input.dispatchMouseEvent", "params": {{"type": "mousePressed", "x": 100, "y": 100}}}}
"""
    
    messages = [
        {"role": "system", "content": system_prompt}
    ] + memory.get_messages()
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            AGNES_API_URL,
            json={
                "model": AI_MODEL,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 500
            },
            headers={"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"},
            timeout=30.0
        )
        
        result = resp.json()["choices"][0]["message"]["content"]
        memory.add("assistant", result)
        return result

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
                # Проверяем параметры
                method = data.get("method")
                params = data.get("params", {})
                cmd_info = get_full_command_info(method)
                
                if cmd_info:
                    required = [p.get("name") for p in cmd_info.get("parameters", []) 
                               if p.get("optional") is not True]
                    missing = [p for p in required if p not in params]
                    
                    if missing:
                        # Если не хватает параметров — логируем и возвращаем None
                        print(f"⚠️ Не хватает параметров: {missing} для {method}")
                        return None
                
                return data
    except Exception as e:
        print(f"⚠️ Ошибка парсинга: {e}")
    return None

def clear_memory():
    memory.clear()
    print("🧹 Память очищена")