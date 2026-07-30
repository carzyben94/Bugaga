import os
import sys
import stat
import time
import logging
import base64
import asyncio
import json
import httpx
import warnings
from collections import Counter
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from datetime import datetime

warnings.filterwarnings("ignore")

# ============================================================
# ПРИНУДИТЕЛЬНЫЙ ВЫВОД В КОНСОЛЬ ДЛЯ RAILWAY
# ============================================================

def log(msg):
    """Вывод в консоль с принудительным сбросом буфера"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

# ============================================================
# НАСТРОЙКА ПУТЕЙ
# ============================================================

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
os.makedirs(LOGS_DIR, exist_ok=True)

# Настройка логирования для файла (для сохранения)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'bot.log'), encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

log(f"✅ agent_workspace: {agent_workspace}")
log(f"✅ helpers_file: {helpers_file}")
log(f"✅ logs_dir: {LOGS_DIR}")

sys.path.insert(0, "browser-harness/src")

from browser_harness.helpers import (
    new_tab, goto_url, wait_for_load, press_key, scroll, js,
    list_tabs, current_tab, close_tab, switch_tab
)
from browser_harness.admin import ensure_daemon

# ============================================================
# ТОКЕН
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

# ============================================================
# БРАУЗЕР
# ============================================================

os.environ["BU_CDP_URL"] = "http://localhost:9222"
ensure_daemon()
log("✅ Браузер готов")

# ============================================================
# DOM ПАРСЕР
# ============================================================

def parse_dom():
    """Парсит DOM страницы"""
    try:
        log("🔍 Запуск parse_dom()")
        js_code = """
        const result = {
            textareas: [],
            buttons: [],
            divs: []
        };
        
        document.querySelectorAll('textarea, button, div[role="button"]').forEach(el => {
            const info = {
                tag: el.tagName.toLowerCase(),
                text: el.textContent?.trim() || '',
                className: el.className || '',
                cssSelector: '',
                visible: el.offsetParent !== null
            };
            
            if (el.id) info.cssSelector = '#' + el.id;
            else if (el.className) info.cssSelector = el.tagName.toLowerCase() + '.' + el.className.split(' ').filter(c => c).join('.');
            else info.cssSelector = el.tagName.toLowerCase();
            
            if (el.tagName.toLowerCase() === 'textarea') result.textareas.push(info);
            else if (el.tagName.toLowerCase() === 'button' || el.getAttribute('role') === 'button') result.buttons.push(info);
            else result.divs.push(info);
        });
        
        return JSON.stringify(result);
        """
        result = js(js_code)
        log("✅ DOM собран")
        return json.loads(result) if result else None
    except Exception as e:
        log(f"❌ Ошибка DOM: {e}")
        return None

# ============================================================
# ПАРСИНГ СООБЩЕНИЙ QWEN
# ============================================================

def parse_messages():
    """Парсит сообщения из чата Qwen"""
    try:
        log("🔍 Запуск parse_messages()")
        js_code = """
        const msgs = [];
        document.querySelectorAll('div, span, p, article').forEach(el => {
            const text = el.textContent?.trim() || '';
            if (text.length < 10) return;
            if (text.includes('How can I help you')) return;
            if (text.includes('Search Chats')) return;
            if (text.includes('New Chat')) return;
            
            const bg = window.getComputedStyle(el).backgroundColor || '';
            const isDark = bg.includes('rgb(30') || bg.includes('rgb(40') || bg.includes('#1a');
            
            msgs.push({
                text: text,
                isUser: isDark,
                isAssistant: !isDark
            });
        });
        
        const unique = [];
        const seen = new Set();
        for (const m of msgs.reverse()) {
            const key = m.text.substring(0, 50);
            if (!seen.has(key)) {
                seen.add(key);
                unique.push(m);
            }
            if (unique.length >= 10) break;
        }
        
        return JSON.stringify(unique);
        """
        result = js(js_code)
        if result:
            data = json.loads(result)
            log(f"📊 Найдено сообщений: {len(data)}")
            return data
        return []
    except Exception as e:
        log(f"❌ Ошибка парсинга сообщений: {e}")
        return []

# ============================================================
# КОМАНДЫ
# ============================================================

async def start(update, context):
    log("📨 Команда /start")
    await update.message.reply_text(
        "🤖 **Qwen Bot на Railway**\n\n"
        "/qwen <текст> — спросить Qwen\n"
        "/read — прочитать чат\n"
        "/clear — очистить чат\n"
        "/status — статус\n"
        "/dom <url> — парсинг DOM"
    )

async def qwen(update, context):
    """Отправить запрос в Qwen"""
    log("=" * 50)
    log("🔥 КОМАНДА /qwen ВЫЗВАНА!")
    log("=" * 50)
    
    try:
        if not context.args:
            log("❌ Нет аргументов")
            await update.message.reply_text("❌ Напиши вопрос\nПример: /qwen Привет!")
            return
        
        query = ' '.join(context.args)
        log(f"📩 Вопрос: {query[:50]}...")
        
        msg = await update.message.reply_text(f"💬 Отправляю: {query[:50]}...")
        log("✅ Статусное сообщение отправлено")
        
        # Открываем Qwen
        log("🔍 Проверяю URL...")
        dom = parse_dom()
        if dom:
            # Проверяем, открыт ли Qwen
            # ... (остальной код)
            
        # Ищем поле ввода
        log("🔍 Ищу поле ввода...")
        for attempt in range(10):
            dom = parse_dom()
            if dom:
                textareas = dom.get('textareas', [])
                log(f"📝 Найдено textarea: {len(textareas)}")
                
                for ta in textareas:
                    if 'message-input-textarea' in ta.get('className', ''):
                        css = ta.get('cssSelector')
                        log(f"✅ Найдено поле ввода: {css}")
                        if css:
                            # Вводим текст
                            log(f"✏️ Ввожу текст: {query[:50]}...")
                            js_code = f"""
                            const el = document.querySelector(`{css}`);
                            if (el) {{
                                el.focus();
                                el.value = '';
                                el.value = `{query}`;
                                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            }}
                            """
                            js(js_code)
                            await asyncio.sleep(0.5)
                            log("⌨️ Нажимаю Enter...")
                            press_key('Enter')
                            break
                if textareas:
                    break
            await asyncio.sleep(2)
        
        log("⏳ Жду ответ...")
        await msg.edit_text("⏳ Qwen думает...")
        
        # Ждем ответ
        timeout = 60
        start_time = time.time()
        last_text = ""
        
        while time.time() - start_time < timeout:
            await asyncio.sleep(3)
            log(f"🔄 Проверка ответа...")
            messages = parse_messages()
            
            if messages:
                for m in messages:
                    if m.get('isAssistant'):
                        answer = m.get('text', '')
                        if answer and answer != query and answer != last_text:
                            last_text = answer
                            log(f"✅ ОТВЕТ ПОЛУЧЕН! Длина: {len(answer)}")
                            await msg.edit_text(f"🤖 **Qwen:**\n\n{answer[:2000]}")
                            return
        
        log("⏰ Таймаут")
        await msg.edit_text("⏰ Превышено время ожидания")
        
    except Exception as e:
        log(f"❌ Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def read(update, context):
    """Прочитать сообщения"""
    log("📖 Команда /read")
    messages = parse_messages()
    if not messages:
        await update.message.reply_text("📭 Нет сообщений")
        return
    
    response = "💬 **Сообщения:**\n\n"
    for i, m in enumerate(messages[-5:], 1):
        author = "👤 Вы" if m.get('isUser') else "🤖 Qwen"
        text = m.get('text', '')[:200]
        response += f"{author}:\n{text}...\n\n"
    
    await update.message.reply_text(response)

async def status(update, context):
    """Статус"""
    log("📊 Команда /status")
    dom = parse_dom()
    if not dom:
        await update.message.reply_text("❌ DOM не получен")
        return
    
    response = f"📊 **Статус**\n\n"
    response += f"🔘 Кнопок: {len(dom.get('buttons', []))}\n"
    response += f"📝 Инпутов: {len(dom.get('textareas', []))}\n"
    
    messages = parse_messages()
    response += f"💬 Сообщений: {len(messages)}"
    
    await update.message.reply_text(response)

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    log("🚀 Запуск бота...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("qwen", qwen))
    app.add_handler(CommandHandler("read", read))
    app.add_handler(CommandHandler("status", status))
    
    log("✅ Бот запущен на Railway!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()