import os
import json
import httpx
from typing import Dict, Optional

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
AGNES_API_URL = os.environ.get("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")
AI_MODEL = "agnes-2.0-flash"

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
    """Возвращает список всех CDP-команд для промпта"""
    if not BROWSER_DOMAINS:
        return "Протоколы не загружены"
    
    lines = []
    for domain in BROWSER_DOMAINS.get("domains", []):
        domain_name = domain.get("domain")
        for cmd in domain.get("commands", []):
            cmd_name = cmd.get("name")
            desc = cmd.get("description", "")[:80]
            lines.append(f"  {domain_name}.{cmd_name} — {desc}")
    
    return "\n".join(lines[:30])  # Ограничим для токенов

async def get_response(user_msg: str) -> str:
    """Отвечает через Agnes AI с контекстом CDP"""
    
    system_prompt = f"""Ты агент, управляющий браузером через CDP (Chrome DevTools Protocol).

Твоя задача — понять запрос пользователя и вернуть JSON с CDP-командой, если требуется действие в браузере.

Доступные команды:
{get_all_commands()}

Формат ответа для команд:
```json
{{"method": "Domain.command", "params": {{...}}}}