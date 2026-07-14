import json
import requests
from config import AGNES_API_KEY, AGNES_API_URL, AI_MODEL

SYSTEM_PROMPT_COMMAND = """You are a smart AI assistant that understands user commands.

🔥 IMPORTANT: ALWAYS respond with JSON only!

RECOGNIZE THESE COMMANDS (in ANY language):
1. Questions about page (ask):
   - "what buttons do you see?" → {"action": "ask", "question": "what buttons are on the page?"}
   - "какие кнопки есть?" → {"action": "ask", "question": "what buttons are on the page?"}
   - "what fields are there?" → {"action": "ask", "question": "what input fields are on the page?"}
   - "какие поля есть?" → {"action": "ask", "question": "what input fields are on the page?"}

2. Click actions (click):
   - "нажми Обзор" → {"action": "click", "target": "Обзор"}
   - "click Explore" → {"action": "click", "target": "Explore"}
   - "нажми Поиск" → {"action": "click", "target": "Search"}

3. Type actions (type):
   - "введи текст в поиск" → {"action": "type", "text": "текст", "field": "поиск"}
   - "type hello in search" → {"action": "type", "text": "hello", "field": "search"}

4. Navigation (navigate):
   - "зайди на x.com" → {"action": "navigate", "url": "https://x.com"}
   - "go to google" → {"action": "navigate", "url": "https://google.com"}

5. Other:
   - "сделай скриншот" → {"action": "screenshot"}
   - "вернись назад" → {"action": "back"}

🔥 RULES:
- ALWAYS respond with JSON only
- If you don't understand → {"action": "unknown"}

Current user said: """

SYSTEM_PROMPT_ANSWER = """You are a helpful assistant that answers questions about web pages.

🔥 IMPORTANT RULES:
1. Return ONLY plain text, NOT JSON!
2. Group elements by type (buttons, inputs, links, menus)
3. Sort within groups: visible first, hidden last
4. Use bullet points with emojis

FORMAT EXAMPLE:
🔘 **Visible Buttons:**
1. Home (visible)
2. Explore (visible)

🔘 **Hidden Buttons:**
3. Settings (hidden)

✏️ **Input Fields:**
1. Search (visible)

Current page context:
"""

def ask_ai_for_command(text, memory=None):
    if not AGNES_API_KEY:
        return {'action': 'error', 'message': 'AGNES_API_KEY не указан'}
    
    system_prompt = SYSTEM_PROMPT_COMMAND
    if memory:
        context = memory.get_context_for_ai()
        if context:
            system_prompt += f"\n\nCONTEXT:\n{context}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text}
    ]
    
    headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
    data = {"model": AI_MODEL, "messages": messages, "temperature": 0.1, "max_tokens": 200}
    
    try:
        response = requests.post(AGNES_API_URL, headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            answer = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            try:
                return json.loads(answer)
            except:
                return {'action': 'unknown'}
        return {'action': 'error', 'message': f"HTTP {response.status_code}"}
    except Exception as e:
        return {'action': 'error', 'message': str(e)}

def ask_ai_for_answer(prompt, context=None, memory=None):
    if not AGNES_API_KEY:
        return "❌ AGNES_API_KEY is not set"
    
    system_prompt = SYSTEM_PROMPT_ANSWER
    if memory:
        memory_context = memory.get_context_for_ai()
        if memory_context:
            system_prompt += f"\n{memory_context}"
    
    messages = [{"role": "system", "content": system_prompt}]
    if context:
        messages.append({"role": "user", "content": f"Page structure:\n{context}"})
    messages.append({"role": "user", "content": f"Question: {prompt}"})
    
    headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
    data = {"model": AI_MODEL, "messages": messages, "temperature": 0.7, "max_tokens": 600}
    
    try:
        response = requests.post(AGNES_API_URL, headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            return result.get("choices", [{}])[0].get("message", {}).get("content", "Нет ответа")
        return f"❌ Ошибка: HTTP {response.status_code}"
    except Exception as e:
        return f"❌ Ошибка: {e}"