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
    def __init__(self, max_history: int = 10):
        self.history: List[Dict[str, str]] = []
        self.max_history = max_history
        self.context: Dict = {}
    
    def add(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
        if len(self.history) > self.max_history:
            self.history.pop(0)
    
    def get_messages(self) -> List[Dict[str, str]]:
        return self.history
    
    def clear(self):
        self.history = []
        self.context = {}
    
    def set_context(self, key: str, value: any):
        self.context[key] = value
    
    def get_context(self, key: str):
        return self.context.get(key)

memory = AgentMemory()

def load_protocols():
    try:
        with open(BROWSER_PROTOCOL, 'r') as f:
            return json.load(f)
    except:
        return None

BROWSER_DOMAINS = load_protocols()

def get_all_commands() -> str:
    if not BROWSER_DOMAINS:
        return "Протоколы не загружены"
    lines = []
    for domain in BROWSER_DOMAINS.get("domains", []):
        for cmd in domain.get("commands", []):
            lines.append(f"  {domain.get('domain')}.{cmd.get('name')}")
    return "\n".join(lines[:30])

async def get_response(user_msg: str, user_id: str = None) -> str:
    if not AGNES_API_KEY:
        return "❌ AGNES_API_KEY не задан"
    
    # Добавляем сообщение пользователя в память
    memory.add("user", user_msg)
    
    # Формируем системный промпт
    system_prompt = f"""Ты агент с доступом к CDP-командам:
{get_all_commands()}

Если нужен браузер — верни JSON:
{{"method": "Domain.command", "params": {{...}}}}
Иначе ответь текстом.

Учитывай историю диалога при ответе."""
    
    # Собираем все сообщения (система + история)
    messages = [
        {"role": "system", "content": system_prompt}
    ] + memory.get_messages()
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            AGNES_API_URL,
            json={
                "model": AI_MODEL,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 500
            },
            headers={"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"},
            timeout=30.0
        )
        
        result = resp.json()["choices"][0]["message"]["content"]
        
        # Сохраняем ответ агента в память
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
                return data
    except:
        pass
    return None

def clear_memory():
    memory.clear()
    print("🧹 Память очищена")

def get_memory():
    return memory.get_messages()