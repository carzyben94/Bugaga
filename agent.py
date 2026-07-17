import os
import json
import httpx
from typing import Dict, Optional

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
AGNES_API_URL = os.environ.get("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")
AI_MODEL = os.environ.get("AI_MODEL", "agnes-2.0-flash")
PROTOCOLS_DIR = os.environ.get("PROTOCOLS_DIR", "/app/docs")
BROWSER_PROTOCOL = os.path.join(PROTOCOLS_DIR, "browser_protocol.json")

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

async def get_response(user_msg: str) -> str:
    if not AGNES_API_KEY:
        return "❌ AGNES_API_KEY не задан"
    
    system_prompt = f"""Ты агент с доступом к CDP-командам:
{get_all_commands()}

Если нужен браузер — верни JSON:
{{"method": "Domain.command", "params": {{...}}}}
Иначе ответь текстом."""
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            AGNES_API_URL,
            json={
                "model": AI_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg}
                ]
            },
            headers={"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"},
            timeout=30.0
        )
        return resp.json()["choices"][0]["message"]["content"]

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