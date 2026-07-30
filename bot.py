import os
import sys
import time
import asyncio
import json
import logging
import httpx
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================================

LOGS_DIR = '/app/logs'
os.makedirs(LOGS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'bot.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] {msg}", flush=True)
    logging.info(msg)

# ============================================================
# ПУТИ
# ============================================================

agent_workspace = "/app/browser-harness/agent-workspace"
sys.path.insert(0, agent_workspace)
sys.path.insert(0, "browser-harness/src")

# ============================================================
# ИМПОРТЫ BROWSER-HARNESS
# ============================================================

from browser_harness.helpers import (
    new_tab, goto_url, wait_for_load, press_key, js,
    list_tabs, current_tab, close_tab
)
from browser_harness.admin import ensure_daemon

# ============================================================
# КУКИ (WebSocket)
# ============================================================

try:
    from cookies import COOKIES
    import websockets
    
    async def set_cookies_async():
        try:
            resp = httpx.get("http://localhost:9222/json/list", timeout=5.0)
            pages = resp.json()
            if not pages:
                log("❌ Нет активных вкладок")
                return False
            ws_url = pages[0]["webSocketDebuggerUrl"]
            log("🔗 Подключаюсь к WebSocket...")
            async with websockets.connect(ws_url) as ws:
                await ws.send(json.dumps({
                    "id": 1,
                    "method": "Network.setCookies",
                    "params": {"cookies": COOKIES}
                }))
                response = json.loads(await ws.recv())
                if "error" in response:
                    log(f"❌ CDP ошибка: {response['error']}")
                    return False
                log(f"🍪 Установлено {len(COOKIES)} кук")
                return True
        except Exception as e:
            log(f"❌ Ошибка установки кук: {e}")
            return False
    
    def set_cookies():
        try:
            loop = asyncio.get_running_loop()
            return asyncio.run_coroutine_threadsafe(set_cookies_async(), loop).result(timeout=10)
        except RuntimeError:
            return asyncio.run(set_cookies_async())
        except Exception as e:
            log(f"❌ Ошибка: {e}")
            return False

except ImportError:
    log("⚠️ websockets не установлен")
    COOKIES = []
    def set_cookies():
        return False

# ============================================================
# НАСТРОЙКА
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

os.environ["BU_CDP_URL"] = "http://localhost:9222"
ensure_daemon()
log("✅ Браузер готов")

set_cookies()
log("✅ Куки установлены")

# ============================================================
# ПАРСИНГ DOM
# ============================================================

def get_dom():
    """Получить DOM элементы страницы"""
    try:
        js_code = """
        const result = {
            textareas: [],
            buttons: [],
            inputs: []
        };
        
        document.querySelectorAll('textarea').forEach(el => {
            result.textareas.push({
                id: el.id || '',
                className: el.className || '',
                placeholder: el.placeholder || '',
                visible: el.offsetParent !== null
            });
        });
        
        document.querySelectorAll('button, [role="button"]').forEach(el => {
            result.buttons.push({
                id: el.id || '',
                className: el.className || '',
                text: (el.textContent?.trim() || '').substring(0, 50),
                visible: el.offsetParent !== null
            });
        });
        
        document.querySelectorAll('input').forEach(el => {
            result.inputs.push({
                id: el.id || '',
                className: el.className || '',
                type: el.type || '',
                placeholder: el.placeholder || '',
                visible: el.offsetParent !== null
            });
        });
        
        return JSON.stringify(result);
        """
        result = js(js_code)
        return json.loads(result) if result else None
    except Exception as e:
        log(f"❌ Ошибка get_dom: {e}")
        return None

# ============================================================
# ПАРСИНГ СООБЩЕНИЙ (ИСПРАВЛЕННЫЙ)
# ============================================================

def get_messages():
    """Получить сообщения из чата"""
    try:
        js_code = """
        const messages = [];
        const blacklist = [
            'How can I help you',
            'Search Chats',
            'New Chat',
            'Toggle sidebar',
            'QR code',
            'scan the QR',
            'download',
            'Press and hold',
            'Kuvaff',
            'Qwen Studio',
            'Select Model',
            'Temporary Chat',
            'Show shortcuts',
            'Voice Input',
            'Voice mode',
            'Upload files'
        ];
        
        document.querySelectorAll('div, span, p, article, section').forEach(el => {
            const text = el.textContent?.trim() || '';
            if (text.length < 10) return;
            
            let skip = false;
            for (const word of blacklist) {
                if (text.includes(word)) {
                    skip = true;
                    break;
                }
            }
            if (skip) return;
            
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return;
            
            const bg = window.getComputedStyle(el).backgroundColor || '';
            const isDark = bg.includes('rgb(30') || bg.includes('rgb(40') || 
                           bg.includes('#1a') || bg.includes('#2d') || 
                           bg.includes('rgb(20') || bg.includes('rgb(10'));
            
            const inChat = el.closest('[role="log"]') || 
                          el.closest('.chat-container') ||
                          el.closest('.message-list') ||
                          el.closest('[class*="message"]');
            
            if (inChat || text.length > 50) {
                messages.push({
                    text: text,
                    isUser: isDark,
                    isAssistant: !isDark,
                    inChat: !!inChat
                });
            }
        });
        
        const unique = [];
        const seen = new Set();
        const sorted = messages.sort((a, b) => (b.inChat ? 1 : 0) - (a.inChat ? 1 : 0));
        
        for (const m of sorted) {
            const key = m.text.substring(0, 50);
            if (!seen.has(key)) {
                seen.add(key);
                unique.push(m);
            }
            if (unique.length >= 15) break;
        }
        
        return JSON.stringify(unique);
        """
        result = js(js_code)
        messages = json.loads(result) if result else []
        
        filtered = []
        for m in messages:
            text = m.get('text', '')
            if len(text) < 10:
                continue
            if any(word in text for word in ['QR', 'scan', 'download', 'Press and hold']):
                continue
            filtered.append(m)
        
        return filtered
    except Exception as e:
        log(f"❌ Ошибка get_messages: {e}")
        return []

# ============================================================
# ОТКРЫТИЕ QWEN
# ============================================================

def open_qwen():
    """Открыть Qwen Chat"""
    try:
        log("🌐 Открываю Qwen Chat...")
        
        tabs = list_tabs()
        for tab in tabs:
            if tab != current_tab():
                try:
                    close_tab(tab)
                except:
                    pass
        
        new_tab()
        time.sleep(1)
        goto_url("https://chat.qwen.ai/")
        wait_for_load(timeout=30)
        time.sleep(5)
        log("✅ Qwen Chat открыт")
        return True
    except Exception as e:
        log(f"❌ Ошибка открытия Qwen: {e}")
        return False

# ============================================================
# ОТПРАВКА СООБЩЕНИЯ
# ============================================================

def send_message(text):
    """Отправить сообщение в Qwen"""
    try:
        log(f"✏️ Отправляю: {text[:50]}...")
        
        for attempt in range(10):
            dom = get_dom()
            if not dom:
                time.sleep(1)
                continue
            
            textareas = dom.get('textareas', [])
            target = None
            
            for ta in textareas:
                if 'message-input-textarea' in ta.get('className', ''):
                    target = ta
                    break
            
            if target:
                css = target.get('cssSelector')
                if css:
                    js_code = f"""
                    const el = document.querySelector(`{css}`);
                    if (el) {{
                        el.focus();
                        el.value = '';
                        el.value = `{text}`;
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('keydown', {{ bubbles: true }}));
                    }}
                    """
                    js(js_code)
                    time.sleep(0.5)
                    press_key('Enter')
                    log("✅ Сообщение отправлено")
                    return True
            
            time.sleep(2)
        
        log("❌ Не найдено поле ввода")
        return False
    except Exception as e:
        log(f"❌ Ошибка отправки: {e}")
        return False

# ============================================================
# ОЖИДАНИЕ ОТВЕТА
# ============================================================

def wait_for_response(query, timeout=90):
    """Ожидать ответ от Qwen"""
    log("⏳ Жду ответ...")
    start_time = time.time()
    last_text = ""
    last_count = 0
    
    while time.time() - start_time < timeout:
        time.sleep(3)
        messages = get_messages()
        
        if messages and len(messages) > last_count:
            new_messages = messages[last_count:]
            for msg in new_messages:
                if msg.get('isAssistant') and not msg.get('isUser'):
                    answer = msg.get('text', '')
                    if (answer and 
                        answer != query and 
                        answer != last_text and
                        len(answer) > 10 and
                        not any(word in answer for word in ['QR', 'scan', 'download'])):
                        log(f"✅ Ответ получен! Длина: {len(answer)}")
                        return answer
            last_count = len(messages)
        
        log("🔄 Проверяю...")
    
    log("⏰ Таймаут")
    return None

# ============================================================
# КОМАНДЫ TELEGRAM
# ============================================================

async def start(update, context):
    await update.message.reply_text(
        "🤖 **Qwen Bot**\n\n"
        "/qwen <текст> — спросить Qwen\n"
        "/read — прочитать чат\n"
        "/clear — очистить чат\n"
        "/status — статус\n"
        "/debug — показать DOM\n"
        "/log — скачать логи"
    )

async def qwen(update, context):
    """Отправить запрос в Qwen"""
    log("=" * 50)
    log("🔥 КОМАНДА /qwen")
    log("=" * 50)
    
    if not context.args:
        await update.message.reply_text("❌ Напиши вопрос\nПример: /qwen Привет!")
        return
    
    query = ' '.join(context.args)
    log(f"📩 Вопрос: {query[:50]}...")
    
    msg = await update.message.reply_text(f"💬 Отправляю: {query[:50]}...")
    
    try:
        if not open_qwen():
            await msg.edit_text("❌ Не удалось открыть Qwen")
            return
        
        if not send_message(query):
            await msg.edit_text("❌ Не удалось отправить сообщение")
            return
        
        await msg.edit_text("⏳ Qwen думает...")
        
        answer = wait_for_response(query, timeout=90)
        
        if answer:
            if len(answer) <= 2000:
                await msg.edit_text(f"🤖 **Qwen:**\n\n{answer}")
            else:
                await msg.edit_text(f"🤖 **Qwen:**\n\n{answer[:2000]}\n\n...(продолжение в файле)")
        else:
            await msg.edit_text("⏰ Превышено время ожидания")
            
    except Exception as e:
        log(f"❌ Ошибка: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def read(update, context):
    """Прочитать сообщения"""
    log("📖 Команда /read")
    
    messages = get_messages()
    if not messages:
        await update.message.reply_text("📭 Нет сообщений")
        return
    
    response = "💬 **Сообщения:**\n\n"
    for i, m in enumerate(messages[-5:], 1):
        author = "👤 Вы" if m.get('isUser') else "🤖 Qwen"
        text = m.get('text', '')[:300]
        response += f"{author}:\n{text}\n\n"
    
    await update.message.reply_text(response)

async def clear(update, context):
    """Очистить чат"""
    log("🧹 Команда /clear")
    
    try:
        if not open_qwen():
            await update.message.reply_text("❌ Не удалось открыть Qwen")
            return
        
        dom = get_dom()
        if dom:
            buttons = dom.get('buttons', [])
            for btn in buttons:
                if 'New Chat' in btn.get('text', ''):
                    css = btn.get('cssSelector')
                    if css:
                        js_code = f"""
                        const el = document.querySelector(`{css}`);
                        if (el) el.click();
                        """
                        js(js_code)
                        await update.message.reply_text("✅ Чат очищен")
                        return
        
        goto_url("https://chat.qwen.ai/")
        wait_for_load(timeout=30)
        await update.message.reply_text("✅ Страница перезагружена")
        
    except Exception as e:
        log(f"❌ Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def status(update, context):
    """Статус"""
    log("📊 Команда /status")
    
    dom = get_dom()
    if not dom:
        await update.message.reply_text("❌ Не удалось получить DOM")
        return
    
    response = f"📊 **Статус Qwen Chat**\n\n"
    response += f"🔘 Кнопок: {len(dom.get('buttons', []))}\n"
    response += f"📝 Текстовых полей: {len(dom.get('textareas', []))}\n"
    response += f"📥 Инпутов: {len(dom.get('inputs', []))}\n"
    
    messages = get_messages()
    response += f"💬 Сообщений: {len(messages)}"
    
    await update.message.reply_text(response)

async def debug_dom(update, context):
    """Показать все элементы DOM для отладки"""
    try:
        await update.message.reply_text("🔍 Сканирую DOM...")
        
        js_code = """
        const result = {
            textareas: [],
            buttons: [],
            inputs: []
        };
        
        document.querySelectorAll('textarea').forEach(el => {
            result.textareas.push({
                id: el.id || '',
                className: el.className || '',
                placeholder: el.placeholder || '',
                visible: el.offsetParent !== null
            });
        });
        
        document.querySelectorAll('button, [role="button"]').forEach(el => {
            result.buttons.push({
                id: el.id || '',
                className: el.className || '',
                text: (el.textContent?.trim() || '').substring(0, 50),
                visible: el.offsetParent !== null
            });
        });
        
        document.querySelectorAll('input').forEach(el => {
            result.inputs.push({
                id: el.id || '',
                className: el.className || '',
                type: el.type || '',
                placeholder: el.placeholder || '',
                visible: el.offsetParent !== null
            });
        });
        
        return JSON.stringify(result);
        """
        
        result = js(js_code)
        data = json.loads(result) if result else None
        
        if not data:
            await update.message.reply_text("❌ Не удалось получить DOM")
            return
        
        response = "📋 **ВСЕ ЭЛЕМЕНТЫ DOM:**\n\n"
        
        response += f"📝 **Textarea ({len(data.get('textareas', []))}):**\n"
        for i, ta in enumerate(data.get('textareas', [])[:5], 1):
            response += f"{i}. id={ta.get('id')}, class={ta.get('className')[:30]}, placeholder={ta.get('placeholder')}, visible={ta.get('visible')}\n"
        if len(data.get('textareas', [])) > 5:
            response += f"... и еще {len(data.get('textareas', [])) - 5}\n"
        response += "\n"
        
        response += f"🔘 **Buttons ({len(data.get('buttons', []))}):**\n"
        for i, btn in enumerate(data.get('buttons', [])[:5], 1):
            response += f"{i}. id={btn.get('id')}, class={btn.get('className')[:30]}, text={btn.get('text')[:30]}, visible={btn.get('visible')}\n"
        if len(data.get('buttons', [])) > 5:
            response += f"... и еще {len(data.get('buttons', [])) - 5}\n"
        response += "\n"
        
        response += f"📥 **Inputs ({len(data.get('inputs', []))}):**\n"
        for i, inp in enumerate(data.get('inputs', [])[:5], 1):
            response += f"{i}. id={inp.get('id')}, type={inp.get('type')}, placeholder={inp.get('placeholder')}, visible={inp.get('visible')}\n"
        if len(data.get('inputs', [])) > 5:
            response += f"... и еще {len(data.get('inputs', [])) - 5}\n"
        
        await update.message.reply_text(response)
            
    except Exception as e:
        log(f"❌ Ошибка debug_dom: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def get_logs(update, context):
    """Отправить полные логи"""
    try:
        await update.message.reply_text("📥 Собираю логи...")
        
        log_file = os.path.join(LOGS_DIR, 'bot.log')
        
        if not os.path.exists(log_file):
            await update.message.reply_text("📭 Лог-файл не найден")
            return
        
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = f.read()
        
        if len(logs) > 4000:
            filename = f"logs_{int(time.time())}.txt"
            file_path = os.path.join(LOGS_DIR, filename)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write(f"ЛОГ ОТ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")
                f.write(logs)
            
            with open(file_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=filename,
                    caption="📄 Полный лог-файл"
                )
            
            try:
                os.remove(file_path)
            except:
                pass
        else:
            await update.message.reply_text(
                f"📋 **ЛОГ-ФАЙЛ:**\n\n```\n{logs}\n```",
                parse_mode='Markdown'
            )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    log("🚀 Запуск бота...")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("qwen", qwen))
    app.add_handler(CommandHandler("read", read))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("debug", debug_dom))
    app.add_handler(CommandHandler("log", get_logs))
    
    log("✅ Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()