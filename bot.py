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
    capture_screenshot, click_at_xy,
    type_text, press_key, fill_input, upload_file,
    page_info, http_get, cdp,
    ensure_real_tab, drain_events, iframe_target
)
from browser_harness.admin import ensure_daemon

# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
Ты — агент, который генерирует Python-код для Browser Harness.

Доступные функции (НЕ используй import):
- new_tab(url=None) — создать вкладку
- goto_url(url) — перейти по URL
- wait_for_load(timeout) — ждать загрузки
- js(expression) — выполнить JavaScript
- list_tabs() — список вкладок
- switch_tab(target_id) — переключиться на вкладку
- current_tab() — ID текущей вкладки
- close_tab() — закрыть текущую вкладку
- ensure_real_tab() — переключиться на реальную вкладку
- click_at_xy(x, y) — клик по координатам
- fill_input(selector, text) — заполнить поле ввода
- type_text(text) — напечатать текст
- press_key(key) — нажать клавишу
- upload_file(selector, paths) — загрузить файл
- capture_screenshot(path) — скриншот
- page_info() — информация о странице
- http_get(url) — HTTP запрос
- cdp(method, **params) — CDP команда
- drain_events() — получить CDP события
- iframe_target(url_substr) — найти iframe по URL

Для скролла используй js("window.scrollBy(0, 500);")

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

def escape_js(text):
    """Экранирует текст для использования в JavaScript строке"""
    if not text:
        return ''
    return text.replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')

def extract_code(text):
    match = re.search(r'```python\s*([\s\S]*?)\s*```', text)
    return match.group(1).strip() if match else None

def execute_harness_code(code):
    """Выполняет код в контексте Browser Harness"""
    import io
    import contextlib
    
    harness_functions = {
        'new_tab': new_tab, 'goto_url': goto_url, 'wait_for_load': wait_for_load,
        'js': js, 'list_tabs': list_tabs, 'current_tab': current_tab,
        'close_tab': close_tab, 'switch_tab': switch_tab,
        'ensure_real_tab': ensure_real_tab,
        'capture_screenshot': capture_screenshot,
        'click_at_xy': click_at_xy,
        'type_text': type_text, 'press_key': press_key,
        'fill_input': fill_input, 'upload_file': upload_file,
        'page_info': page_info, 'http_get': http_get,
        'cdp': cdp, 'drain_events': drain_events,
        'iframe_target': iframe_target,
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
        "/tabs — список вкладок\n"
        "/tab_new — открыть вкладку\n"
        "/tab_close <номер> — закрыть вкладку\n"
        "/tab_switch <номер> — переключить вкладку\n"
        "/log — скачать логи"
    )

async def log(update, context):
    """Скачать логи бота"""
    try:
        log_file = os.path.join(LOGS_DIR, 'bot.log')
        if not os.path.exists(log_file):
            await update.message.reply_text("📭 Лог-файл не найден")
            return
        
        size = os.path.getsize(log_file)
        with open(log_file, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename='bot.log',
                caption=f"📋 Логи бота ({size} байт)"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def z(update, context):
    if not context.args:
        await update.message.reply_text("❌ /z <запрос>")
        return
    
    query = " ".join(context.args)
    logger.info(f"📝 /z запрос: {query}")
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
        
        query_escaped = escape_js(query)
        
        js_code = f"""
        (function() {{
            const input = document.querySelector('#chat-input');
            if (!input) return;
            input.value = '';
            input.focus();
            input.value = '{query_escaped}';
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
        
        if response and len(response) > 5:
            await status.edit_text(f"🤖 {response}", parse_mode=None)
        else:
            await status.edit_text("❌ Нет ответа")
            
    except Exception as e:
        logger.error(f"❌ /z ошибка: {e}")
        await status.edit_text(f"❌ Ошибка: {str(e)}")

async def z_logic(query):
    """Вспомогательная функция для Z.ai с подробным логированием"""
    logger.info(f"📤 z_logic: запрос длиной {len(query)} символов")
    logger.info(f"📤 z_logic: первые 200 символов: {query[:200]}...")
    
    try:
        # Закрываем старые вкладки
        tabs = list_tabs()
        logger.info(f"📑 z_logic: открыто вкладок: {len(tabs)}")
        
        for tab in tabs:
            if tab != current_tab():
                try: 
                    close_tab(tab)
                    logger.info(f"🗑️ z_logic: закрыта вкладка {tab}")
                except Exception as e:
                    logger.warning(f"⚠️ z_logic: не удалось закрыть вкладку: {e}")

        logger.info("🌐 z_logic: открываю новую вкладку с chat.z.ai")
        new_tab("https://chat.z.ai/")
        wait_for_load(30)
        logger.info("✅ z_logic: страница загружена")
        await asyncio.sleep(2)

        # Экранируем запрос
        query_escaped = escape_js(query)
        logger.info(f"✍️ z_logic: экранированный запрос: {query_escaped[:100]}...")

        js_code = f"""
        (function() {{
            const input = document.querySelector('#chat-input');
            if (!input) return '❌ Поле ввода не найдено';
            input.value = '';
            input.focus();
            input.value = '{query_escaped}';
            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            const btn = document.querySelector('#send-message-button');
            if (btn && !btn.disabled) {{
                btn.click();
                return '✅ Клик по кнопке';
            }} else {{
                input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', bubbles: true }}));
                return '✅ Enter';
            }}
        }})();
        """
        
        logger.info("📤 z_logic: выполняю JS для отправки запроса")
        result = js(js_code)
        logger.info(f"📥 z_logic: результат отправки: {result}")
        
        logger.info("⏳ z_logic: жду 30 секунд...")
        await asyncio.sleep(30)

        logger.info("📤 z_logic: получаю ответ")
        response = js("""
        (function() {
            const el = document.querySelector('.chat-assistant');
            if (!el) return '';
            const paragraphs = el.querySelectorAll('p');
            const texts = [];
            for (const p of paragraphs) {
                const t = p.textContent?.trim();
                if (t) texts.push(t);
            }
            return texts.join('\\n\\n');
        })();
        """)
        
        logger.info(f"📥 z_logic: получен ответ длиной {len(response) if response else 0} символов")
        
        if response and len(response) > 5:
            logger.info("✅ z_logic: ответ получен успешно")
            return response
        else:
            logger.warning("⚠️ z_logic: ответ пустой или слишком короткий")
            return None
        
    except Exception as e:
        logger.error(f"❌ z_logic: ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

async def agent(update, context):
    if not context.args:
        await update.message.reply_text("❌ /agent <задание>")
        return
    
    task = " ".join(context.args)
    logger.info(f"🧠 Агент: запрос пользователя: {task}")
    
    status = await update.message.reply_text(f"🧠 Агент: {task}...")
    
    # 1. Генерируем код через Z.ai
    full_query = f"{SYSTEM_PROMPT}\n\nЗапрос: {task}"
    logger.info(f"📤 Агент: полный запрос к Z.ai: {full_query[:200]}...")
    
    code_response = await z_logic(full_query)
    
    if not code_response:
        logger.error("❌ Агент: не удалось получить код от Z.ai")
        await status.edit_text("❌ Не удалось сгенерировать код. Проверьте логи.")
        return
    
    logger.info(f"📥 Агент: получен ответ от Z.ai: {code_response[:200]}...")
    
    code = extract_code(code_response)
    if not code:
        logger.error("❌ Агент: код не найден в ответе")
        logger.error(f"📄 Агент: полный ответ: {code_response}")
        await status.edit_text(f"❌ Нет кода в ответе:\n{code_response[:500]}")
        return
    
    logger.info(f"✅ Агент: код извлечён, длина {len(code)} символов")
    await status.edit_text(f"📝 Код:\n```python\n{code}\n```")
    
    # 2. Выполняем код
    logger.info("⚡ Агент: выполняю код...")
    await status.edit_text("⚡ Выполняю...")
    result = execute_harness_code(code)
    
    if result:
        logger.info(f"✅ Агент: результат выполнения: {result[:200]}...")
        await status.edit_text(f"✅ Результат:\n{result[:4000]}")
    else:
        logger.warning("⚠️ Агент: код выполнен без вывода")
        await status.edit_text("✅ Выполнено (без вывода)")

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
    app.add_handler(CommandHandler("log", log))
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