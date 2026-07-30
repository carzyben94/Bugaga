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

# Логирование в файл И в консоль
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'bot.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def log(msg):
    """Вывод в консоль с временем"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] {msg}", flush=True)
    # Также пишем в лог-файл
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
            divs: []
        };
        
        document.querySelectorAll('textarea, button, [role="button"], div').forEach(el => {
            const info = {
                tag: el.tagName.toLowerCase(),
                text: el.textContent?.trim() || '',
                className: el.className || '',
                cssSelector: '',
                visible: el.offsetParent !== null
            };
            
            if (el.id) {
                info.cssSelector = '#' + el.id;
            } else if (el.className) {
                info.cssSelector = el.tagName.toLowerCase() + '.' + el.className.split(' ').filter(c => c).join('.');
            } else {
                info.cssSelector = el.tagName.toLowerCase();
            }
            
            if (el.tagName.toLowerCase() === 'textarea') {
                result.textareas.push(info);
            } else if (el.tagName.toLowerCase() === 'button' || el.getAttribute('role') === 'button') {
                result.buttons.push(info);
            } else {
                result.divs.push(info);
            }
        });
        
        return JSON.stringify(result);
        """
        result = js(js_code)
        return json.loads(result) if result else None
    except Exception as e:
        log(f"❌ Ошибка get_dom: {e}")
        return None

# ============================================================
# ПАРСИНГ СООБЩЕНИЙ (УЛУЧШЕННЫЙ)
# ============================================================

def get_messages():
    """Получить сообщения из чата (только реальные диалоги)"""
    try:
        js_code = """
        const messages = [];
        
        // ЧЕРНЫЙ СПИСКОК — текст, который игнорируем
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
        
        // Ищем все текстовые элементы
        document.querySelectorAll('div, span, p, article, section').forEach(el => {
            const text = el.textContent?.trim() || '';
            if (text.length < 10) return;
            
            // Пропускаем черный список
            let skip = false;
            for (const word of blacklist) {
                if (text.includes(word)) {
                    skip = true;
                    break;
                }
            }
            if (skip) return;
            
            // Проверяем, что элемент видимый
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return;
            
            // Проверяем фон для определения автора
            const bg = window.getComputedStyle(el).backgroundColor || '';
            const isDark = bg.includes('rgb(30') || bg.includes('rgb(40') || 
                           bg.includes('#1a') || bg.includes('#2d') || 
                           bg.includes('rgb(20') || bg.includes('rgb(10'));
            
            // Проверяем, есть ли элемент в контейнере чата
            const inChat = el.closest('[role="log"]') || 
                          el.closest('.chat-container') ||
                          el.closest('.message-list') ||
                          el.closest('[class*="message"]');
            
            // Если текст длинный или в чате — сохраняем
            if (inChat || text.length > 50) {
                messages.push({
                    text: text,
                    isUser: isDark,
                    isAssistant: !isDark,
                    inChat: !!inChat
                });
            }
        });
        
        // Убираем дубликаты и сортируем
        const unique = [];
        const seen = new Set();
        
        // Сначала сообщения из чата (приоритет)
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
        
        # Дополнительная фильтрация в Python
        filtered = []
        for m in messages:
            text = m.get('text', '')
            # Пропускаем слишком короткие
            if len(text) < 10:
                continue
            # Пропускаем мусор
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
        
        # Закрываем старые вкладки
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
        time.sleep(5)  # Даем больше времени на загрузку
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
        
        # Ищем поле ввода
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
                    # Вводим текст
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
# ОЖИДАНИЕ ОТВЕТА (УЛУЧШЕННОЕ)
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
            # Проверяем новые сообщения
            new_messages = messages[last_count:]
            for msg in new_messages:
                if msg.get('isAssistant') and not msg.get('isUser'):
                    answer = msg.get('text', '')
                    # Проверяем, что это не наш запрос и не мусор
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
        # Открываем Qwen
        if not open_qwen():
            await msg.edit_text("❌ Не удалось открыть Qwen")
            return
        
        # Отправляем сообщение
        if not send_message(query):
            await msg.edit_text("❌ Не удалось отправить сообщение")
            return
        
        await msg.edit_text("⏳ Qwen думает...")
        
        # Ждем ответ
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
        
        # Ищем кнопку New Chat
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
        
        # Если не нашли кнопку - перезагружаем
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
    
    messages = get_messages()
    response += f"💬 Сообщений: {len(messages)}"
    
    await update.message.reply_text(response)

# ============================================================
# КОМАНДА /log
# ============================================================

async def get_logs(update, context):
    """Отправить полные логи для отладки"""
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
    app.add_handler(CommandHandler("log", get_logs))
    
    log("✅ Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()