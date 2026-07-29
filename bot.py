# bot.py
import os
import sys
import time
import logging
import json
import re
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================================
# НАСТРОЙКА
# ============================================================

LOGS_DIR = '/app/logs'
os.makedirs(LOGS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'bot.log')),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Подключаем Browser Harness
sys.path.insert(0, "browser-harness/src")

from browser_harness.helpers import (
    new_tab, goto_url, wait_for_load, js,
    list_tabs, current_tab, close_tab, switch_tab,
    capture_screenshot, click_at_xy, scroll_at_xy,
    type_text, press_key, fill_input, upload_file,
    page_info, http_get, cdp
)
from browser_harness.admin import ensure_daemon

# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
Ты — агент, который генерирует Python-код для Browser Harness.

Доступные функции:
- new_tab(url=None), goto_url(url), wait_for_load(timeout)
- list_tabs(), switch_tab(id), current_tab(), close_tab()
- js(code), click_at_xy(x,y), fill_input(sel,text)
- type_text(text), press_key(key), scroll_at_xy(x,y,dy,dx)
- capture_screenshot(path), page_info(), http_get(url)
- upload_file(sel, paths), cdp(method, **params)

Правила:
1. Возвращай ТОЛЬКО код в ```python ... ```
2. НЕ используй import
3. Используй print() для вывода
4. После goto_url() вызывай wait_for_load()
5. Используй fill_input() для ввода текста
"""

# ============================================================
# ФУНКЦИИ
# ============================================================

def extract_code(text):
    match = re.search(r'```python\s*([\s\S]*?)\s*```', text)
    return match.group(1).strip() if match else None

def execute_harness_code(code):
    """Выполняет код в контексте Browser Harness"""
    import io
    import contextlib
    
    # Все функции Harness уже в глобальном пространстве
    harness_functions = {
        'new_tab': new_tab, 'goto_url': goto_url, 'wait_for_load': wait_for_load,
        'js': js, 'list_tabs': list_tabs, 'current_tab': current_tab,
        'close_tab': close_tab, 'switch_tab': switch_tab,
        'capture_screenshot': capture_screenshot, 'click_at_xy': click_at_xy,
        'scroll_at_xy': scroll_at_xy, 'type_text': type_text,
        'press_key': press_key, 'fill_input': fill_input,
        'upload_file': upload_file, 'page_info': page_info,
        'http_get': http_get, 'cdp': cdp,
        'print': print, 'time': time, 'sleep': time.sleep
    }
    
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            exec(code, harness_functions)
        return output.getvalue()
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

# ============================================================
# КОМАНДЫ
# ============================================================

async def start(update, context):
    await update.message.reply_text(
        "🌐 Браузер бот\n\n"
        "/z <запрос> — спросить Z.ai\n"
        "/agent <запрос> — агент выполняет код в браузере\n"
        "/dom <url> — скачать DOM\n"
        "/tabs — список вкладок"
    )

async def z(update, context):
    if not context.args:
        await update.message.reply_text("❌ /z <запрос>")
        return
    
    query = " ".join(context.args)
    status = await update.message.reply_text("🤖 Запрос к Z.ai...")
    
    try:
        # Закрываем старые вкладки
        for tab in list_tabs():
            if tab != current_tab():
                try: close_tab(tab)
                except: pass
        
        new_tab("https://chat.z.ai/")
        wait_for_load(30)
        await asyncio.sleep(2)
        
        # Отправляем запрос
        js_code = f"""
        (function() {{
            const input = document.querySelector('#chat-input');
            if (!input) return;
            input.value = '';
            input.focus();
            input.value = '{query.replace("'", "\\'")}';
            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            const btn = document.querySelector('#send-message-button');
            if (btn && !btn.disabled) btn.click();
            else input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', bubbles: true }}));
        }})();
        """
        js(js_code)
        
        await asyncio.sleep(30)
        
        # Получаем ответ
        response = js("""
        (function() {
            const el = document.querySelector('.chat-assistant');
            if (!el) return '';
            return Array.from(el.querySelectorAll('p'))
                .map(p => p.textContent?.trim())
                .filter(t => t)
                .join('\\n\\n');
        })();
        """)
        
        if response and len(response) > 5:
            await status.edit_text(f"🤖 {response}", parse_mode=None)
        else:
            await status.edit_text("❌ Нет ответа")
            
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {str(e)}")

async def agent(update, context):
    if not context.args:
        await update.message.reply_text("❌ /agent <задание>")
        return
    
    task = " ".join(context.args)
    status = await update.message.reply_text(f"🧠 Агент: {task}...")
    
    # 1. Генерируем код
    code_response = await z_logic(f"{SYSTEM_PROMPT}\n\nЗапрос: {task}")
    if not code_response:
        await status.edit_text("❌ Не удалось сгенерировать код")
        return
    
    code = extract_code(code_response)
    if not code:
        await status.edit_text(f"❌ Нет кода:\n{code_response[:200]}")
        return
    
    await status.edit_text(f"📝 Код:\n```python\n{code}\n```")
    
    # 2. Выполняем код
    await status.edit_text("⚡ Выполняю...")
    result = execute_harness_code(code)
    
    if result:
        await status.edit_text(f"✅ Результат:\n{result[:4000]}")
    else:
        await status.edit_text("✅ Выполнено")

# Вспомогательная функция для Z.ai
async def z_logic(query):
    try:
        for tab in list_tabs():
            if tab != current_tab():
                try: close_tab(tab)
                except: pass
        
        new_tab("https://chat.z.ai/")
        wait_for_load(30)
        await asyncio.sleep(2)
        
        js_code = f"""
        (function() {{
            const input = document.querySelector('#chat-input');
            if (!input) return;
            input.value = '';
            input.focus();
            input.value = '{query.replace("'", "\\'")}';
            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            const btn = document.querySelector('#send-message-button');
            if (btn && !btn.disabled) btn.click();
            else input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', bubbles: true }}));
        }})();
        """
        js(js_code)
        
        await asyncio.sleep(30)
        
        response = js("""
        (function() {
            const el = document.querySelector('.chat-assistant');
            if (!el) return '';
            return Array.from(el.querySelectorAll('p'))
                .map(p => p.textContent?.trim())
                .filter(t => t)
                .join('\\n\\n');
        })();
        """)
        
        return response if response and len(response) > 5 else None
        
    except Exception as e:
        logger.error(f"z_logic error: {e}")
        return None

async def dom(update, context):
    if not context.args:
        await update.message.reply_text("❌ /dom <url>")
        return
    
    url = context.args[0].strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    status = await update.message.reply_text(f"🌐 {url}...")
    
    try:
        new_tab(url)
        wait_for_load(30)
        
        result = js("""
        const all = document.querySelectorAll('*');
        const data = [];
        for (const el of all) {
            const text = el.textContent?.trim() || '';
            if (!text || text.length < 1) continue;
            data.push({
                tag: el.tagName.toLowerCase(),
                text: text.substring(0, 200),
                id: el.id || '',
                class: el.className || ''
            });
        }
        return JSON.stringify(data.slice(0, 50));
        """)
        
        if result:
            await status.edit_text(f"📊 DOM:\n{result[:3000]}")
        else:
            await status.edit_text("❌ Нет данных")
            
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {str(e)}")

async def tabs(update, context):
    try:
        tabs = list_tabs()
        if not tabs:
            await update.message.reply_text("📭 Нет вкладок")
            return
        
        current = current_tab()
        text = "📑 Вкладки:\n\n"
        for i, tab in enumerate(tabs, 1):
            text += f"{'✅' if tab == current else '🔲'} {i}. {tab}\n"
        
        text += "\n/tab_new, /tab_close <номер>, /tab_switch <номер>"
        await update.message.reply_text(text)
        
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)}")

async def tab_new(update, context):
    try:
        new_tab()
        await update.message.reply_text("✅ Новая вкладка")
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)}")

async def tab_close(update, context):
    if not context.args:
        await update.message.reply_text("❌ /tab_close <номер>")
        return
    
    try:
        num = int(context.args[0]) - 1
        tabs = list_tabs()
        if 0 <= num < len(tabs):
            if tabs[num] == current_tab() and len(tabs) > 1:
                await update.message.reply_text("❌ Нельзя закрыть текущую")
                return
            close_tab()
            await update.message.reply_text(f"✅ Закрыта")
        else:
            await update.message.reply_text("❌ Нет такой вкладки")
    except:
        await update.message.reply_text("❌ Ошибка")

async def tab_switch(update, context):
    if not context.args:
        await update.message.reply_text("❌ /tab_switch <номер>")
        return
    
    try:
        num = int(context.args[0]) - 1
        tabs = list_tabs()
        if 0 <= num < len(tabs):
            switch_tab(tabs[num])
            await update.message.reply_text(f"✅ Переключено на {num + 1}")
        else:
            await update.message.reply_text("❌ Нет такой вкладки")
    except:
        await update.message.reply_text("❌ Ошибка")

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

    os.environ["BU_CDP_URL"] = "http://localhost:9222"
    ensure_daemon()
    logger.info("✅ Браузер готов")

    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("z", z))
    app.add_handler(CommandHandler("agent", agent))
    app.add_handler(CommandHandler("dom", dom))
    app.add_handler(CommandHandler("tabs", tabs))
    app.add_handler(CommandHandler("tab_new", tab_new))
    app.add_handler(CommandHandler("tab_close", tab_close))
    app.add_handler(CommandHandler("tab_switch", tab_switch))

    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()