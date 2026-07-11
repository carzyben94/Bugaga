import os
import logging
import json
import subprocess
import time
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters, MessageHandler
import websockets
import base64
import re

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

AGNES_API_KEY = os.getenv("AGNES_API_KEY")
AGNES_API_URL = os.getenv("AGNES_API_URL", "https://api.agnes.ai/v1/chat/completions")

CHROME_PATH = "/usr/bin/google-chrome"
chrome_ws_url = None
cdp_protocol = None
cdp_full_docs = ""  # Полная документация в текстовом виде

# ---------- Загрузка CDP протокола ----------

def load_cdp_protocol():
    """Загружает полную спецификацию CDP"""
    global cdp_protocol, cdp_full_docs
    
    try:
        response = requests.get("http://localhost:9222/json/protocol")
        cdp_protocol = response.json()
        
        # Преобразуем в читаемый текст
        cdp_full_docs = format_cdp_docs(cdp_protocol)
        
        logger.info(f"✅ Загружена CDP спецификация: {len(cdp_protocol.get('domains', []))} доменов")
        logger.info(f"📄 Размер документации: {len(cdp_full_docs)} символов")
        return cdp_protocol
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки CDP протокола: {e}")
        return None

def format_cdp_docs(protocol):
    """Преобразует CDP протокол в читаемый текст для агента"""
    docs = []
    docs.append("# ПОЛНАЯ СПЕЦИФИКАЦИЯ CDP (Chrome DevTools Protocol)\n")
    
    for domain in protocol.get("domains", []):
        domain_name = domain.get("domain", "")
        docs.append(f"\n## Домен: {domain_name}")
        docs.append(f"Описание: {domain.get('description', 'Нет описания')}\n")
        
        # Команды
        if domain.get("commands"):
            docs.append(f"### Команды ({len(domain['commands'])}):")
            for cmd in domain["commands"]:
                cmd_name = cmd.get("name", "")
                docs.append(f"\n#### {domain_name}.{cmd_name}")
                docs.append(f"Описание: {cmd.get('description', 'Нет описания')}")
                
                if cmd.get("parameters"):
                    docs.append("Параметры:")
                    for param in cmd["parameters"]:
                        name = param.get("name", "")
                        ptype = param.get("type", "any")
                        desc = param.get("description", "")
                        optional = " (опционально)" if param.get("optional") else ""
                        docs.append(f"  - {name}: {ptype}{optional} - {desc}")
                
                if cmd.get("returns"):
                    docs.append("Возвращает:")
                    for ret in cmd["returns"]:
                        name = ret.get("name", "")
                        rtype = ret.get("type", "any")
                        desc = ret.get("description", "")
                        docs.append(f"  - {name}: {rtype} - {desc}")
        
        # События
        if domain.get("events"):
            docs.append(f"\n### События ({len(domain['events'])}):")
            for event in domain["events"]:
                event_name = event.get("name", "")
                docs.append(f"\n#### {domain_name}.{event_name}")
                docs.append(f"Описание: {event.get('description', 'Нет описания')}")
                
                if event.get("parameters"):
                    docs.append("Параметры:")
                    for param in event["parameters"]:
                        name = param.get("name", "")
                        ptype = param.get("type", "any")
                        desc = param.get("description", "")
                        docs.append(f"  - {name}: {ptype} - {desc}")
        
        # Типы
        if domain.get("types"):
            docs.append(f"\n### Типы ({len(domain['types'])}):")
            for typ in domain["types"]:
                typ_name = typ.get("id", "")
                docs.append(f"\n#### {domain_name}.{typ_name}")
                docs.append(f"Описание: {typ.get('description', 'Нет описания')}")
                
                if typ.get("properties"):
                    docs.append("Свойства:")
                    for prop in typ["properties"]:
                        name = prop.get("name", "")
                        ptype = prop.get("type", "any")
                        desc = prop.get("description", "")
                        docs.append(f"  - {name}: {ptype} - {desc}")
        
        docs.append("\n" + "-" * 50 + "\n")
    
    return "\n".join(docs)

# ---------- Agnes AI с ВСЕЙ документацией ----------

async def ask_agnes(prompt: str, context: str = "") -> dict:
    """Отправляет запрос к Agnes API с ПОЛНОЙ документацией CDP"""
    
    if not AGNES_API_KEY:
        raise ValueError("AGNES_API_KEY не установлен!")
    
    global cdp_full_docs
    
    # Загружаем протокол если ещё нет
    if not cdp_full_docs:
        load_cdp_protocol()
    
    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Обрезаем документацию если слишком большая (для токенов)
    max_docs_len = 10000  # Ограничиваем для экономии токенов
    docs_to_send = cdp_full_docs[:max_docs_len]
    if len(cdp_full_docs) > max_docs_len:
        docs_to_send += f"\n... (документация обрезана, всего {len(cdp_full_docs)} символов)"
    
    system_prompt = f"""
    Ты AI-агент с ПОЛНЫМ контролем над браузером через CDP (Chrome DevTools Protocol).
    
    Вот ПОЛНАЯ документация CDP:
    
    {docs_to_send}
    
    📚 Твои инструменты (вызывай через JSON):
    1. **search_cdp(query)** - искать в документации
    2. **exec_cdp(domain, command, params)** - выполнить ЛЮБУЮ CDP команду
    3. **eval_js(js_code)** - выполнить произвольный JavaScript
    
    Ты можешь делать ВСЁ! Просто найди нужную команду в документации и выполни её.
    
    ОТВЕЧАЙ В ФОРМАТЕ JSON:
    {{
        "reasoning": "почему я выбрал эти действия",
        "actions": [
            {{"tool": "search_cdp", "params": {{"query": "Page.navigate"}}}},
            {{"tool": "exec_cdp", "params": {{"domain": "Page", "command": "navigate", "params": {{"url": "https://google.com"}}}}}}
        ]
    }}
    
    Если нужно просто ответить:
    {{
        "reasoning": "просто отвечаю",
        "actions": []
    }}
    """
    
    data = {
        "model": "agnes-v1",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Контекст: {context}\nЗапрос: {prompt}"}
        ],
        "temperature": 0.3,
        "max_tokens": 2000
    }
    
    try:
        response = requests.post(AGNES_API_URL, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = response.json()
        
        content = result["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except:
            return {"reasoning": "прямой ответ", "actions": [], "message": content}
            
    except Exception as e:
        logger.error(f"Agnes API error: {e}")
        return {"reasoning": "ошибка", "actions": [], "error": str(e)}

# ---------- Остальной код (CDP команды, обработчики и т.д.) ----------

# ... (все остальные функции из предыдущего кода остаются без изменений)

def main() -> None:
    if not start_chrome():
        logger.warning("⚠️ Chrome не запустился")
    
    get_websocket_url()
    load_cdp_protocol()  # Загружаем ВСЮ документацию
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cdp", cdp_command))
    app.add_handler(CommandHandler("docs", docs_command))
    app.add_handler(CommandHandler("domains", domains_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Бот с ПОЛНОЙ CDP документацией запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()