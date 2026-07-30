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
# НАСТРОЙКА
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
SCREENSHOTS_DIR = '/app/screenshots'
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# Логирование в файл
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
    new_tab, goto_url, wait_for_load, page_info, capture_screenshot,
    click_at_xy, type_text, press_key, scroll, js, cdp, ensure_real_tab,
    wait_for_element, list_tabs, current_tab, close_tab, switch_tab,
    fill_input, upload_file, http_get, drain_events
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
                await ws.send(json.dumps({"id": 1, "method": "Network.setCookies", "params": {"cookies": COOKIES}}))
                response = json.loads(await ws.recv())
                if "error" in response:
                    log(f"❌ CDP ошибка: {response['error']}")
                    return False
                log(f"🍪 Установлено {len(COOKIES)} кук")
                return True
        except Exception as e:
            log(f"❌ Ошибка: {e}")
            return False
    
    def set_cookies_global():
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
    def set_cookies_global():
        return False

# ============================================================
# НАСТРОЙКА РАЗМЕРА ОКНА (WebSocket)
# ============================================================

async def set_viewport_async():
    try:
        resp = httpx.get("http://localhost:9222/json/list", timeout=5.0)
        pages = resp.json()
        if not pages:
            log("⚠️ Нет активных вкладок для установки размера")
            return False
        ws_url = pages[0]["webSocketDebuggerUrl"]
        log("🔗 Подключаюсь к WebSocket для установки размера...")
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({
                "id": 2,
                "method": "Emulation.setDeviceMetricsOverride",
                "params": {
                    "width": 1280,
                    "height": 720,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                    "screenWidth": 1280,
                    "screenHeight": 720,
                    "positionX": 0,
                    "positionY": 0
                }
            }))
            response = json.loads(await ws.recv())
            if "error" in response:
                log(f"⚠️ CDP ошибка: {response['error']}")
                return False
            log("✅ Размер окна установлен: 1280x720")
            return True
    except Exception as e:
        log(f"⚠️ Не удалось установить размер окна: {e}")
        return False

def set_viewport_global():
    try:
        loop = asyncio.get_running_loop()
        return asyncio.run_coroutine_threadsafe(set_viewport_async(), loop).result(timeout=10)
    except RuntimeError:
        return asyncio.run(set_viewport_async())
    except Exception as e:
        log(f"⚠️ Не удалось установить размер окна: {e}")
        return False

# ============================================================
# НАСТРОЙКА
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

os.environ["BU_CDP_URL"] = "http://localhost:9222"
ensure_daemon()
log("✅ Браузер готов")

set_cookies_global()
set_viewport_global()

# ============================================================
# GITHUB
# ============================================================

def push_to_github(content, filename, host="x.com"):
    if not GITHUB_TOKEN:
        log("⚠️ GITHUB_TOKEN не задан")
        return False

    repo = "carzyben94/Bugaga"
    branch = "main"
    file_path = f"browser-harness/agent-workspace/domain-skills/{host}/{filename}"
    url = f"https://api.github.com/repos/{repo}/contents/{file_path}"

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        resp = httpx.get(url, headers=headers, timeout=10)
        sha = resp.json().get("sha") if resp.status_code == 200 else None
    except Exception:
        sha = None

    data = {
        "message": f"Добавлен/обновлён навык {filename} для {host}",
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch
    }
    if sha:
        data["sha"] = sha

    try:
        response = httpx.put(url, headers=headers, json=data, timeout=30)
        if response.status_code in [200, 201]:
            log(f"✅ Навык отправлен в GitHub: {file_path}")
            return True
        else:
            log(f"❌ Ошибка отправки в GitHub: {response.text}")
            return False
    except Exception as e:
        log(f"❌ Ошибка при отправке в GitHub: {e}")
        return False

# ============================================================
# DOM ПАРСЕР (ПОЛНЫЙ)
# ============================================================

def parse_dom():
    """Парсит DOM страницы и возвращает JSON со всеми интерактивными элементами"""
    try:
        log("🔍 Запуск parse_dom()")
        js_code = """
        function getElementInfo(el) {
            const info = {
                tag: el.tagName.toLowerCase(),
                text: el.textContent?.trim() || '',
                value: el.value || '',
                placeholder: el.placeholder || '',
                type: el.type || '',
                name: el.name || '',
                id: el.id || '',
                className: el.className || '',
                href: el.href || '',
                src: el.src || '',
                alt: el.alt || '',
                title: el.title || '',
                disabled: el.disabled || false,
                readonly: el.readOnly || false,
                required: el.required || false,
                checked: el.checked || false,
                selected: el.selected || false,
                visible: el.offsetParent !== null,
                xpath: '',
                cssSelector: '',
                attributes: {},
                dataAttributes: {}
            };
            
            try {
                const xpath = document.evaluate(
                    './/' + info.tag + 
                    (info.id ? '[@id="' + info.id + '"]' : '') +
                    (info.name ? '[@name="' + info.name + '"]' : '') +
                    (info.className ? '[contains(@class, "' + info.className.split(' ')[0] + '")]' : ''),
                    document.documentElement,
                    null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE,
                    null
                );
                if (xpath.singleNodeValue) {
                    info.xpath = './/' + info.tag + 
                        (info.id ? '[@id="' + info.id + '"]' : '') +
                        (info.name ? '[@name="' + info.name + '"]' : '') +
                        (info.className ? '[contains(@class, "' + info.className.split(' ')[0] + '")]' : '');
                }
            } catch(e) {}
            
            try {
                if (info.id) {
                    info.cssSelector = '#' + info.id;
                } else if (info.className) {
                    info.cssSelector = info.tag + '.' + info.className.split(' ').filter(c => c).join('.');
                } else if (info.name) {
                    info.cssSelector = info.tag + '[name="' + info.name + '"]';
                } else {
                    info.cssSelector = info.tag;
                }
            } catch(e) {}
            
            for (const attr of el.attributes) {
                const name = attr.name;
                const value = attr.value;
                info.attributes[name] = value;
                
                if (name.startsWith('data-')) {
                    info.dataAttributes[name] = value;
                }
            }
            
            const ariaAttrs = ['aria-label', 'aria-describedby', 'aria-labelledby', 
                              'aria-hidden', 'aria-disabled', 'aria-required', 
                              'aria-checked', 'aria-selected', 'aria-expanded'];
            for (const attr of ariaAttrs) {
                if (el.hasAttribute(attr)) {
                    info.attributes[attr] = el.getAttribute(attr);
                }
            }
            
            const testAttrs = ['data-testid', 'data-test', 'data-cy', 'data-qa', 
                              'data-test-id', 'testid', 'test-id'];
            for (const attr of testAttrs) {
                if (el.hasAttribute(attr)) {
                    info.attributes[attr] = el.getAttribute(attr);
                }
            }
            
            return info;
        }
        
        const elements = {
            buttons: [],
            inputs: [],
            links: [],
            forms: [],
            selects: [],
            textareas: [],
            divs: [],
            spans: [],
            lis: [],
            others: []
        };
        
        const selectors = [
            'button',
            'input:not([type="hidden"])',
            'a[href]',
            'form',
            'select',
            'textarea',
            '[role="button"]',
            '[role="link"]',
            '[role="checkbox"]',
            '[role="radio"]',
            '[contenteditable="true"]'
        ];
        
        const allElements = document.querySelectorAll(selectors.join(','));
        const extraSet = new Set(allElements);
        
        const extraElements = document.querySelectorAll('[onclick], [data-testid], [data-test], [data-cy], [data-qa]');
        for (const el of extraElements) {
            if (!extraSet.has(el)) {
                extraSet.add(el);
            }
        }
        
        const finalElements = Array.from(extraSet);
        
        for (const el of finalElements) {
            const info = getElementInfo(el);
            const tag = info.tag;
            
            if (tag === 'button' || el.hasAttribute('role') && el.getAttribute('role') === 'button') {
                elements.buttons.push(info);
            } else if (tag === 'input') {
                elements.inputs.push(info);
            } else if (tag === 'a') {
                elements.links.push(info);
            } else if (tag === 'form') {
                elements.forms.push(info);
            } else if (tag === 'select') {
                elements.selects.push(info);
            } else if (tag === 'textarea') {
                elements.textareas.push(info);
            } else if (tag === 'div') {
                elements.divs.push(info);
            } else if (tag === 'span') {
                elements.spans.push(info);
            } else if (tag === 'li') {
                elements.lis.push(info);
            } else {
                elements.others.push(info);
            }
        }
        
        const pageInfo = {
            url: window.location.href,
            title: document.title,
            timestamp: Date.now()
        };
        
        log('✅ DOM собран');
        return JSON.stringify({ page: pageInfo, elements: elements }, null, 2);
        """
        
        result = js(js_code)
        log(f"📥 Результат parse_dom: {str(result)[:200]}...")
        return result, None
    except Exception as e:
        log(f"❌ Ошибка парсинга DOM: {e}")
        return None, str(e)

# ============================================================
# ПАРСИНГ СООБЩЕНИЙ QWEN
# ============================================================

def parse_qwen_messages():
    """Специальный парсер для сообщений Qwen Chat"""
    try:
        log("🔍 Запуск parse_qwen_messages()")
        
        js_code = """
        function getMessages() {
            const messages = [];
            const selectors = [
                '[data-testid="message"]',
                '[role="log"] [data-testid="message"]',
                '.message-item',
                '.chat-message',
                'article[data-testid="message"]',
                'div[class*="message"]',
                'div[class*="Message"]'
            ];
            
            let messageElements = [];
            for (const selector of selectors) {
                const elements = document.querySelectorAll(selector);
                if (elements.length > 0) {
                    messageElements = elements;
                    break;
                }
            }
            
            if (messageElements.length === 0) {
                const allElements = document.querySelectorAll('div, span, p, article');
                for (const el of allElements) {
                    const text = el.textContent?.trim() || '';
                    if (text.length > 30 && 
                        !text.includes('How can I help you') &&
                        !text.includes('Search Chats') &&
                        !text.includes('Toggle sidebar')) {
                        messageElements.push(el);
                    }
                }
            }
            
            let userMessages = [];
            let assistantMessages = [];
            
            for (const el of messageElements) {
                const text = el.textContent?.trim() || '';
                if (!text || text.length < 10) continue;
                
                const isUser = el.closest('[data-testid="message-user"]') || 
                              el.closest('.user-message') ||
                              el.closest('[class*="user"]') ||
                              el.closest('[data-author="user"]');
                
                const isAssistant = el.closest('[data-testid="message-assistant"]') || 
                                   el.closest('.assistant-message') ||
                                   el.closest('[class*="assistant"]') ||
                                   el.closest('[data-author="assistant"]');
                
                const styles = window.getComputedStyle(el);
                const bgColor = styles.backgroundColor || '';
                const isDarkBg = bgColor.includes('rgb(30') || bgColor.includes('rgb(40') || 
                               bgColor.includes('#1a') || bgColor.includes('#2d');
                
                const message = {
                    text: text,
                    isUser: !!isUser || (isDarkBg && !isAssistant),
                    isAssistant: !!isAssistant || (!isDarkBg && !isUser),
                    timestamp: Date.now()
                };
                
                if (message.isUser) {
                    userMessages.push(message);
                } else if (message.isAssistant) {
                    assistantMessages.push(message);
                } else {
                    if (text.includes('Qwen') || text.includes('I am') || text.includes("I'm")) {
                        message.isAssistant = true;
                        assistantMessages.push(message);
                    } else {
                        message.isUser = true;
                        userMessages.push(message);
                    }
                }
            }
            
            const allMessages = [];
            let uIdx = 0, aIdx = 0;
            
            while (uIdx < userMessages.length || aIdx < assistantMessages.length) {
                if (uIdx < userMessages.length) {
                    allMessages.push({...userMessages[uIdx], role: 'user'});
                    uIdx++;
                }
                if (aIdx < assistantMessages.length) {
                    allMessages.push({...assistantMessages[aIdx], role: 'assistant'});
                    aIdx++;
                }
            }
            
            const recentMessages = allMessages.slice(-20);
            
            return {
                messages: recentMessages,
                total: allMessages.length,
                userCount: userMessages.length,
                assistantCount: assistantMessages.length,
                lastMessage: allMessages.length > 0 ? allMessages[allMessages.length - 1] : null
            };
        }
        
        return JSON.stringify(getMessages());
        """
        
        log("🔄 Выполняю JavaScript...")
        result = js(js_code)
        log(f"📥 Результат JS: {str(result)[:200]}...")
        
        if result:
            log("✅ JS выполнен успешно, парсинг JSON...")
            return json.loads(result)
        log("⚠️ JS вернул None")
        return None
    except Exception as e:
        log(f"❌ Ошибка парсинга сообщений Qwen: {e}")
        return None

# ============================================================
# QWEN CHAT КОМАНДЫ
# ============================================================

async def qwen_send(update, context):
    """Отправить сообщение в Qwen Chat и получить ответ"""
    try:
        log("=" * 50)
        log("🔥 КОМАНДА /qwen ВЫЗВАНА!")
        log("=" * 50)
        
        if not context.args:
            log("❌ Нет аргументов")
            await update.message.reply_text(
                "❌ Напиши сообщение для Qwen\n"
                "Пример: /qwen Привет! Как дела?"
            )
            return
        
        query = ' '.join(context.args).strip()
        log(f"📩 ПОЛУЧЕН ЗАПРОС: {query[:50]}...")
        
        status_msg = await update.message.reply_text(f"💬 Отправляю запрос в Qwen: {query[:50]}...")
        log("✅ Статусное сообщение отправлено")
        
        # Проверяем, открыт ли Qwen Chat
        try:
            log("🔍 Проверяю, открыт ли Qwen Chat...")
            dom_data, _ = parse_dom()
            if dom_data:
                dom_json = json.loads(dom_data)
                current_url = dom_json.get('page', {}).get('url', '')
                log(f"🌐 Текущий URL: {current_url}")
                
                if 'chat.qwen.ai' not in current_url:
                    log("🔄 Qwen не открыт, открываю...")
                    tabs = list_tabs()
                    for tab in tabs:
                        if tab != current_tab():
                            try:
                                close_tab(tab)
                            except:
                                pass
                    
                    new_tab()
                    await asyncio.sleep(1)
                    goto_url("https://chat.qwen.ai/")
                    wait_for_load(timeout=30)
                    log("✅ Qwen Chat загружен")
                    await status_msg.edit_text("✅ Qwen Chat загружен, отправляю запрос...")
                    await asyncio.sleep(2)
            else:
                log("🔄 DOM не получен, открываю Qwen...")
                new_tab()
                await asyncio.sleep(1)
                goto_url("https://chat.qwen.ai/")
                wait_for_load(timeout=30)
                log("✅ Qwen Chat загружен")
                await status_msg.edit_text("✅ Qwen Chat загружен, отправляю запрос...")
                await asyncio.sleep(2)
                
        except Exception as e:
            log(f"❌ Ошибка загрузки Qwen: {e}")
            await status_msg.edit_text(f"❌ Ошибка загрузки Qwen: {str(e)[:200]}")
            return
        
        # Находим поле ввода и отправляем сообщение
        try:
            log("🔍 Ищу поле ввода...")
            textarea_found = False
            for attempt in range(10):
                dom_data, _ = parse_dom()
                if not dom_data:
                    log(f"⚠️ Попытка {attempt+1}: DOM не получен")
                    await asyncio.sleep(1)
                    continue
                
                dom_json = json.loads(dom_data)
                textareas = dom_json.get('elements', {}).get('textareas', [])
                log(f"📝 Найдено textarea: {len(textareas)}")
                
                target_textarea = None
                for ta in textareas:
                    if 'message-input-textarea' in ta.get('className', ''):
                        target_textarea = ta
                        log(f"✅ Найдено поле ввода: {ta.get('cssSelector')}")
                        break
                
                if target_textarea:
                    textarea_found = True
                    
                    css_selector = target_textarea.get('cssSelector')
                    if css_selector:
                        log(f"✏️ Ввожу текст: {query[:50]}...")
                        js_code = f"""
                        const el = document.querySelector(`{css_selector}`);
                        if (el) {{
                            el.focus();
                            el.value = '';
                            el.value = `{query}`;
                            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            return true;
                        }}
                        return false;
                        """
                        js(js_code)
                        await asyncio.sleep(0.5)
                        
                        log("⌨️ Нажимаю Enter...")
                        press_key('Enter')
                        await status_msg.edit_text("✉️ Сообщение отправлено, жду ответа...")
                        break
                
                await asyncio.sleep(2)
            
            if not textarea_found:
                log("❌ Не найдено поле ввода Qwen")
                await status_msg.edit_text("❌ Не найдено поле ввода Qwen")
                return
                
        except Exception as e:
            log(f"❌ Ошибка отправки: {e}")
            await status_msg.edit_text(f"❌ Ошибка отправки: {str(e)[:200]}")
            return
        
        # Ждем ответа
        log("⏳ Жду ответ от Qwen...")
        await status_msg.edit_text("⏳ Qwen думает...")
        
        timeout = 120
        start_time = time.time()
        last_message_count = 0
        last_text = ""
        attempt = 0
        
        while time.time() - start_time < timeout:
            await asyncio.sleep(3)
            attempt += 1
            log(f"🔄 Попытка {attempt}: проверяю ответ...")
            
            messages_data = parse_qwen_messages()
            if not messages_data:
                log(f"⚠️ Попытка {attempt}: parse_qwen_messages() вернул None")
                continue
            
            messages = messages_data.get('messages', [])
            log(f"📊 Найдено сообщений: {len(messages)}")
            
            if messages:
                for msg in messages:
                    log(f"📝 Сообщение: {msg.get('text', '')[:50]}... role={msg.get('role')}")
            
            if len(messages) > last_message_count:
                log(f"🆕 Новые сообщения: {len(messages) - last_message_count}")
                new_messages = messages[last_message_count:]
                for msg in new_messages:
                    if msg.get('role') == 'assistant' or msg.get('isAssistant'):
                        answer = msg.get('text', '')
                        log(f"🤖 Найден ответ Qwen: {answer[:100]}...")
                        
                        if answer and answer != query and answer != last_text:
                            last_text = answer
                            log(f"✅ ОТВЕТ ПОЛУЧЕН! Длина: {len(answer)}")
                            
                            if len(answer) <= 2000:
                                await status_msg.edit_text(
                                    f"🤖 **Qwen ответил:**\n\n{answer}",
                                    parse_mode='Markdown'
                                )
                            else:
                                await status_msg.edit_text(
                                    f"🤖 **Qwen ответил:**\n\n{answer[:2000]}\n\n...(продолжение в файле)",
                                    parse_mode='Markdown'
                                )
                                
                                filename = f"qwen_response_{int(time.time())}.txt"
                                file_path = os.path.join(LOGS_DIR, filename)
                                with open(file_path, 'w', encoding='utf-8') as f:
                                    f.write(answer)
                                
                                with open(file_path, 'rb') as f:
                                    await update.message.reply_document(
                                        document=f,
                                        filename=filename,
                                        caption="📄 Полный ответ Qwen"
                                    )
                                
                                try:
                                    os.remove(file_path)
                                except:
                                    pass
                            
                            log("✅ Ответ отправлен в Telegram")
                            return
                
                last_message_count = len(messages)
        
        log("⏰ Таймаут ожидания ответа от Qwen")
        await status_msg.edit_text("⏰ Превышено время ожидания ответа от Qwen (2 минуты)")
        
    except Exception as e:
        log(f"❌ Ошибка в /qwen_send: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def qwen_read(update, context):
    """Прочитать последние сообщения из Qwen Chat"""
    try:
        log("📖 Запрос на чтение сообщений")
        status_msg = await update.message.reply_text("📖 Читаю сообщения...")
        
        messages_data = parse_qwen_messages()
        
        if not messages_data or not messages_data.get('messages'):
            await status_msg.edit_text("📭 Нет сообщений в чате")
            return
        
        messages = messages_data['messages']
        
        response = "💬 **Последние сообщения Qwen Chat:**\n\n"
        
        for i, msg in enumerate(messages[-10:], 1):
            if msg.get('role') == 'user' or msg.get('isUser'):
                author = "👤 **Вы**"
            else:
                author = "🤖 **Qwen**"
            
            text = msg.get('text', '')[:300]
            if len(msg.get('text', '')) > 300:
                text += "..."
            
            response += f"{author}:\n{text}\n\n"
        
        response += f"\n📊 Всего сообщений: {messages_data.get('total', 0)}"
        response += f"\n👤 Ваших: {messages_data.get('userCount', 0)}"
        response += f"\n🤖 Qwen: {messages_data.get('assistantCount', 0)}"
        
        if len(response) > 4000:
            response = response[:4000] + "\n\n... (обрезано)"
        
        await status_msg.edit_text(response, parse_mode='Markdown')
        log("✅ Сообщения отправлены")
        
    except Exception as e:
        log(f"❌ Ошибка в /qwen_read: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def qwen_clear(update, context):
    """Очистить чат Qwen (начать новый диалог)"""
    try:
        log("🧹 Запрос на очистку чата")
        status_msg = await update.message.reply_text("🧹 Очищаю чат...")
        
        try:
            dom_data, _ = parse_dom()
            if dom_data:
                dom_json = json.loads(dom_data)
                if 'chat.qwen.ai' not in dom_json.get('page', {}).get('url', ''):
                    goto_url("https://chat.qwen.ai/")
                    wait_for_load(timeout=30)
            else:
                goto_url("https://chat.qwen.ai/")
                wait_for_load(timeout=30)
            
            await asyncio.sleep(2)
            
            dom_data, _ = parse_dom()
            if dom_data:
                dom_json = json.loads(dom_data)
                
                buttons = dom_json.get('elements', {}).get('buttons', [])
                divs = dom_json.get('elements', {}).get('divs', [])
                
                for btn in buttons:
                    if 'New Chat' in btn.get('text', '') or 'new chat' in btn.get('text', '').lower():
                        css_selector = btn.get('cssSelector')
                        if css_selector:
                            log(f"🔘 Найдена кнопка New Chat: {css_selector}")
                            js_code = f"""
                            const el = document.querySelector(`{css_selector}`);
                            if (el) el.click();
                            """
                            js(js_code)
                            await status_msg.edit_text("✅ Чат очищен, можно начинать новый диалог")
                            log("✅ Чат очищен")
                            await asyncio.sleep(1)
                            return
                
                for div in divs:
                    if 'New Chat' in div.get('text', '') or 'new chat' in div.get('text', '').lower():
                        css_selector = div.get('cssSelector')
                        if css_selector:
                            log(f"🔘 Найдена кнопка New Chat (div): {css_selector}")
                            js_code = f"""
                            const el = document.querySelector(`{css_selector}`);
                            if (el) el.click();
                            """
                            js(js_code)
                            await status_msg.edit_text("✅ Чат очищен, можно начинать новый диалог")
                            log("✅ Чат очищен")
                            await asyncio.sleep(1)
                            return
            
            log("⚠️ Кнопка New Chat не найдена, перезагружаю...")
            await status_msg.edit_text("❌ Не найдена кнопка New Chat, пробую перезагрузить...")
            goto_url("https://chat.qwen.ai/")
            wait_for_load(timeout=30)
            await status_msg.edit_text("✅ Страница перезагружена, чат очищен")
            log("✅ Страница перезагружена")
            
        except Exception as e:
            log(f"❌ Ошибка: {e}")
            await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
            
    except Exception as e:
        log(f"❌ Ошибка в /qwen_clear: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def qwen_status(update, context):
    """Проверить статус Qwen Chat"""
    try:
        log("📊 Запрос статуса Qwen")
        dom_data, _ = parse_dom()
        if not dom_data:
            await update.message.reply_text("❌ Не удалось получить DOM")
            return
        
        dom_json = json.loads(dom_data)
        page = dom_json.get('page', {})
        elements = dom_json.get('elements', {})
        
        response = f"**📊 Qwen Chat Status**\n\n"
        response += f"🌐 URL: {page.get('url', 'unknown')}\n"
        response += f"📝 Title: {page.get('title', 'unknown')}\n\n"
        
        buttons = len(elements.get('buttons', []))
        inputs = len(elements.get('inputs', []))
        textareas = len(elements.get('textareas', []))
        
        response += f"🔘 Кнопок: {buttons}\n"
        response += f"📝 Инпутов: {inputs}\n"
        response += f"📄 Текстовых полей: {textareas}\n\n"
        
        textarea_present = False
        for ta in elements.get('textareas', []):
            if 'message-input-textarea' in ta.get('className', ''):
                textarea_present = True
                break
        
        if textarea_present:
            response += "✅ Поле ввода найдено"
        else:
            response += "❌ Поле ввода не найдено"
        
        messages_data = parse_qwen_messages()
        if messages_data:
            response += f"\n\n💬 Сообщений в чате: {messages_data.get('total', 0)}"
            response += f"\n👤 Ваших: {messages_data.get('userCount', 0)}"
            response += f"\n🤖 Qwen: {messages_data.get('assistantCount', 0)}"
        
        await update.message.reply_text(response, parse_mode='Markdown')
        log("✅ Статус отправлен")
        
    except Exception as e:
        log(f"❌ Ошибка в /qwen_status: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# ОСТАЛЬНЫЕ КОМАНДЫ
# ============================================================

async def start(update, context):
    await update.message.reply_text(
        "🌐 **Браузер-бот с Qwen интеграцией**\n\n"
        "**Qwen Chat команды:**\n"
        "/qwen <текст> — отправить запрос в Qwen\n"
        "/qwen_read — прочитать последние сообщения\n"
        "/qwen_clear — очистить чат\n"
        "/qwen_status — статус Qwen Chat\n\n"
        "**Основные команды:**\n"
        "/dom <url> — парсинг DOM\n"
        "/trends — глобальные тренды X\n"
        "/analyze — анализ вовлеченности\n"
        "/tabs — список вкладок\n"
        "/tab_new — открыть вкладку\n"
        "/tab_close <номер> — закрыть вкладку\n"
        "/tab_switch <номер> — переключить вкладку\n"
        "/log — скачать логи",
        parse_mode='Markdown'
    )

async def log(update, context):
    try:
        log_file = os.path.join(LOGS_DIR, 'bot.log')
        if not os.path.exists(log_file):
            await update.message.reply_text("📭 Лог-файл не найден")
            return
        with open(log_file, 'rb') as f:
            await update.message.reply_document(document=f, filename='bot.log')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def dom(update, context):
    """Парсит DOM указанной страницы"""
    try:
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите URL\n"
                "Пример: /dom https://example.com\n"
                "Пример: /dom x.com"
            )
            return
        
        url = context.args[0].strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        status_msg = await update.message.reply_text(f"🌐 Открываю {url}...")
        
        try:
            new_tab()
            goto_url(url)
            wait_for_load(timeout=30)
            await status_msg.edit_text(f"✅ Страница загружена, парсинг...")
        except Exception as e:
            await status_msg.edit_text(f"❌ Ошибка загрузки: {str(e)[:200]}")
            return
        
        result, error = parse_dom()
        if error:
            await status_msg.edit_text(f"❌ Ошибка парсинга: {error}")
            return
        
        if not result:
            await status_msg.edit_text("❌ Не удалось получить данные DOM")
            return
        
        try:
            dom_data = json.loads(result)
        except:
            await status_msg.edit_text("❌ Ошибка парсинга JSON")
            return
        
        timestamp = int(time.time())
        domain = url.replace('https://', '').replace('http://', '').split('/')[0]
        filename = f"dom_{domain}_{timestamp}.json"
        file_path = os.path.join(LOGS_DIR, filename)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(dom_data, f, ensure_ascii=False, indent=2)
        
        with open(file_path, 'rb') as f:
            await status_msg.edit_text("📄 Отправляю JSON...")
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"📊 DOM страницы\nURL: {dom_data.get('page', {}).get('url', 'unknown')}\nЭлементов: {sum(len(v) for v in dom_data.get('elements', {}).values())}"
            )
        
        elements = dom_data.get('elements', {})
        stats = "📊 **Статистика DOM:**\n\n"
        total = 0
        for key, value in elements.items():
            if value:
                count = len(value)
                total += count
                stats += f"• {key}: {count}\n"
        stats += f"\n**Всего: {total}**"
        
        await update.message.reply_text(stats, parse_mode='Markdown')
        
        try:
            os.remove(file_path)
        except:
            pass
            
    except Exception as e:
        log(f"❌ Ошибка в /dom: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def kalshi(update, context):
    """Парсит последние 5 постов Kalshi"""
    try:
        status_msg = await update.message.reply_text("🔍 Открываю Kalshi...")
        
        try:
            tabs = list_tabs()
            for tab in tabs:
                if tab != current_tab():
                    try:
                        close_tab(tab)
                    except:
                        pass
            
            new_tab()
            await asyncio.sleep(1)
            goto_url("https://x.com/Kalshi")
            wait_for_load(timeout=30)
            await asyncio.sleep(3)
            
            for _ in range(8):
                scroll(0, 600)
                await asyncio.sleep(1.5)
            
            await status_msg.edit_text("✅ Страница загружена, парсинг постов...")
        except Exception as e:
            log(f"Ошибка загрузки: {e}")
            await status_msg.edit_text(f"❌ Ошибка загрузки: {str(e)[:200]}")
            return
        
        js_code = """
        const posts = [];
        const articles = document.querySelectorAll('article[data-testid="tweet"]');
        
        for (const article of articles) {
            try {
                const textEl = article.querySelector('[data-testid="tweetText"]');
                const text = textEl ? textEl.textContent.trim() : '';
                
                const nameEl = article.querySelector('[data-testid="User-Name"]');
                let name = 'Kalshi';
                if (nameEl) {
                    const fullName = nameEl.textContent.trim();
                    const nameParts = fullName.split('@');
                    name = nameParts[0].trim();
                }
                
                const replyEl = article.querySelector('[data-testid="reply"]');
                const replies = replyEl ? replyEl.textContent.trim() : '0';
                
                const retweetEl = article.querySelector('[data-testid="retweet"]');
                const retweets = retweetEl ? retweetEl.textContent.trim() : '0';
                
                const likeEl = article.querySelector('[data-testid="like"]');
                const likes = likeEl ? likeEl.textContent.trim() : '0';
                
                posts.push({
                    text: text,
                    name: name,
                    replies: replies,
                    retweets: retweets,
                    likes: likes
                });
            } catch(e) {}
        }
        
        return JSON.stringify(posts);
        """
        
        result = js(js_code)
        if not result:
            await status_msg.edit_text("❌ Не удалось получить посты")
            return
        
        try:
            posts = json.loads(result)
        except:
            await status_msg.edit_text("❌ Ошибка парсинга JSON")
            return
        
        if not posts:
            await status_msg.edit_text("📭 Постов не найдено. Попробуйте позже.")
            return
        
        posts = posts[:5]
        response = f"📊 **Kalshi — последние 5 постов**\n\n"
        
        for i, post in enumerate(posts, 1):
            response += f"**{i}.** {post.get('name', 'Kalshi')}\n"
            response += f"💬 {post.get('replies', '0')} | 🔄 {post.get('retweets', '0')} | ❤️ {post.get('likes', '0')}\n"
            response += f"📝 {post.get('text', '')[:300]}"
            if len(post.get('text', '')) > 300:
                response += "..."
            response += "\n\n"
        
        await status_msg.edit_text(response, parse_mode='Markdown')
        
    except Exception as e:
        log(f"❌ Ошибка в /kalshi: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def trends(update, context):
    """Анализ глобальных трендов X"""
    try:
        status_msg = await update.message.reply_text("🔍 Открываю глобальные тренды X...")
        
        try:
            tabs = list_tabs()
            for tab in tabs:
                if tab != current_tab():
                    try:
                        close_tab(tab)
                    except:
                        pass
            
            new_tab()
            await asyncio.sleep(1)
            goto_url("https://x.com/explore/tabs/trending")
            wait_for_load(timeout=30)
            await asyncio.sleep(3)
            
            for _ in range(5):
                scroll(0, 600)
                await asyncio.sleep(1.5)
            
            await status_msg.edit_text("🔍 Сканирую тренды...")
        except Exception as e:
            await status_msg.edit_text(f"❌ Ошибка загрузки: {str(e)[:200]}")
            return
        
        js_code = """
        const data = {
            hashtags: [],
            mentions: [],
            keywords: [],
            posts: [],
            trends: []
        };
        
        document.querySelectorAll('span, div[role="article"], article').forEach(el => {
            const text = el.textContent?.trim();
            if (!text || text.length < 2) return;
            
            if (/(\\d+[.,]?\\d*[KMB]?|просмотров|постов|тенденция|Follow|Following|Replying)/i.test(text)) return;
            
            if (text.startsWith('#') || 
                (text.length < 40 && /^[A-ZА-Я]/.test(text) && !text.includes(' '))) {
                data.trends.push(text);
                
                const hashtags = text.match(/#\\w+/g);
                if (hashtags) data.hashtags.push(...hashtags);
                
                const mentions = text.match(/@\\w+/g);
                if (mentions) data.mentions.push(...mentions);
            }
            
            const words = text.split(/\\s+/).filter(w => w.length > 3 && /^[A-ZА-Я]/.test(w) && !/^\\d+$/.test(w));
            if (words) data.keywords.push(...words);
        });
        
        return JSON.stringify(data);
        """
        
        result = js(js_code)
        if not result:
            await status_msg.edit_text("❌ Не удалось получить данные")
            return
        
        try:
            data = json.loads(result)
        except:
            await status_msg.edit_text("❌ Ошибка парсинга JSON")
            return
        
        if not data.get('trends') and not data.get('hashtags'):
            await status_msg.edit_text("📭 Трендов не найдено. Попробуйте позже.")
            return
        
        trend_counts = Counter(data['trends']).most_common(15)
        hashtag_counts = Counter(data['hashtags']).most_common(10)
        mention_counts = Counter(data['mentions']).most_common(5)
        keyword_counts = Counter(data['keywords']).most_common(5)
        
        response = f"🌍 **Глобальные тренды X**\n\n"
        
        if trend_counts:
            response += "**🔥 Топ трендов:**\n"
            for i, (trend, count) in enumerate(trend_counts, 1):
                response += f"{i}. {trend} — {count}\n"
            response += "\n"
        
        if hashtag_counts:
            response += "**# Хэштеги:**\n"
            for i, (tag, count) in enumerate(hashtag_counts, 1):
                response += f"{i}. {tag} — {count}\n"
            response += "\n"
        
        if mention_counts:
            response += "**👥 Упоминания:**\n"
            for i, (mention, count) in enumerate(mention_counts, 1):
                response += f"{i}. {mention} — {count}\n"
            response += "\n"
        
        if keyword_counts:
            response += "**📈 Ключевые слова:**\n"
            for i, (word, count) in enumerate(keyword_counts, 1):
                response += f"{i}. {word} — {count}\n"
        
        await status_msg.edit_text(response, parse_mode='Markdown')
        
    except Exception as e:
        log(f"❌ Ошибка в /trends: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def analyze(update, context):
    """Глубокий анализ вовлеченности глобальных трендов"""
    try:
        status_msg = await update.message.reply_text("📊 Открываю глобальные тренды...")
        
        try:
            tabs = list_tabs()
            for tab in tabs:
                if tab != current_tab():
                    try:
                        close_tab(tab)
                    except:
                        pass
            
            new_tab()
            await asyncio.sleep(1)
            goto_url("https://x.com/explore/tabs/trending")
            wait_for_load(timeout=30)
            await asyncio.sleep(3)
            
            for _ in range(5):
                scroll(0, 600)
                await asyncio.sleep(1.5)
            
            await status_msg.edit_text("📊 Анализирую вовлеченность...")
        except Exception as e:
            await status_msg.edit_text(f"❌ Ошибка загрузки: {str(e)[:200]}")
            return
        
        js_code = """
        const trends = [];
        document.querySelectorAll('span, div[role="article"], article').forEach(el => {
            const text = el.textContent?.trim();
            if (!text || text.length < 2) return;
            if (/(\\d+[.,]?\\d*[KMB]?|просмотров|постов|тенденция|Follow|Following|Replying)/i.test(text)) return;
            
            if (text.startsWith('#') || 
                (text.length < 40 && /^[A-ZА-Я]/.test(text) && !text.includes(' '))) {
                trends.push(text);
            }
        });
        
        const uniqueTrends = [...new Set(trends)];
        return JSON.stringify(uniqueTrends.slice(0, 20));
        """
        
        result = js(js_code)
        if not result:
            await status_msg.edit_text("❌ Не удалось получить данные")
            return
        
        try:
            trends = json.loads(result)
        except:
            await status_msg.edit_text("❌ Ошибка парсинга JSON")
            return
        
        if not trends:
            await status_msg.edit_text("📭 Трендов не найдено")
            return
        
        total_trends = len(trends)
        hashtag_trends = [t for t in trends if t.startswith('#')]
        text_trends = [t for t in trends if not t.startswith('#')]
        
        response = f"📊 **Анализ глобальных трендов**\n\n"
        response += f"📈 Всего трендов: {total_trends}\n"
        response += f"🏷️ Хэштегов: {len(hashtag_trends)}\n"
        response += f"📝 Тем: {len(text_trends)}\n\n"
        
        if hashtag_trends:
            response += "**# Популярные хэштеги:**\n"
            for i, tag in enumerate(hashtag_trends[:5], 1):
                response += f"{i}. {tag}\n"
        
        if text_trends:
            response += "\n**📌 Популярные темы:**\n"
            for i, topic in enumerate(text_trends[:5], 1):
                response += f"{i}. {topic}\n"
        
        await status_msg.edit_text(response, parse_mode='Markdown')
        
    except Exception as e:
        log(f"❌ Ошибка в /analyze: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tabs(update, context):
    """Показать список всех вкладок"""
    try:
        tab_list = list_tabs()
        if not tab_list:
            await update.message.reply_text("📭 Нет открытых вкладок")
            return
        
        current = current_tab()
        response = "📑 Список вкладок:\n\n"
        for i, tab in enumerate(tab_list, 1):
            if tab == current:
                response += f"✅ {i}. {tab} (текущая)\n"
            else:
                response += f"🔲 {i}. {tab}\n"
        
        response += "\nКоманды:\n"
        response += "/tab_new — открыть новую вкладку\n"
        response += "/tab_close <номер> — закрыть вкладку\n"
        response += "/tab_switch <номер> — переключиться на вкладку"
        
        if len(response) > 4000:
            response = response[:4000] + "\n\n... (обрезано)"
        
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tab_new(update, context):
    """Открыть новую вкладку"""
    try:
        new_tab()
        await update.message.reply_text("✅ Новая вкладка открыта")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tab_close(update, context):
    """Закрыть вкладку по номеру"""
    try:
        if not context.args:
            await update.message.reply_text("❌ Укажите номер вкладки\nПример: /tab_close 1")
            return
        
        try:
            tab_num = int(context.args[0]) - 1
        except ValueError:
            await update.message.reply_text("❌ Номер должен быть числом")
            return
        
        tabs_list = list_tabs()
        if tab_num < 0 or tab_num >= len(tabs_list):
            await update.message.reply_text(f"❌ Вкладка с номером {tab_num + 1} не найдена")
            return
        
        tab_id = tabs_list[tab_num]
        current = current_tab()
        
        if tab_id == current and len(tabs_list) > 1:
            await update.message.reply_text("❌ Нельзя закрыть текущую вкладку, если есть другие. Сначала переключитесь на другую.")
            return
        
        close_tab(tab_id)
        await update.message.reply_text(f"✅ Вкладка {tab_num + 1} закрыта")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tab_switch(update, context):
    """Переключиться на вкладку по номеру"""
    try:
        if not context.args:
            await update.message.reply_text("❌ Укажите номер вкладки\nПример: /tab_switch 2")
            return
        
        try:
            tab_num = int(context.args[0]) - 1
        except ValueError:
            await update.message.reply_text("❌ Номер должен быть числом")
            return
        
        tabs_list = list_tabs()
        if tab_num < 0 or tab_num >= len(tabs_list):
            await update.message.reply_text(f"❌ Вкладка с номером {tab_num + 1} не найдена")
            return
        
        tab_id = tabs_list[tab_num]
        switch_tab(tab_id)
        await update.message.reply_text(f"✅ Переключился на вкладку {tab_num + 1}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# ============================================================
# ЗАПУСК
# ============================================================

def main():
    log("🚀 Запуск бота на Railway...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Qwen команды
    app.add_handler(CommandHandler("qwen", qwen_send))
    app.add_handler(CommandHandler("qwen_send", qwen_send))
    app.add_handler(CommandHandler("qwen_read", qwen_read))
    app.add_handler(CommandHandler("qwen_clear", qwen_clear))
    app.add_handler(CommandHandler("qwen_status", qwen_status))
    
    # Основные команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dom", dom))
    app.add_handler(CommandHandler("kalshi", kalshi))
    app.add_handler(CommandHandler("trends", trends))
    app.add_handler(CommandHandler("analyze", analyze))
    app.add_handler(CommandHandler("tabs", tabs))
    app.add_handler(CommandHandler("tab_new", tab_new))
    app.add_handler(CommandHandler("tab_close", tab_close))
    app.add_handler(CommandHandler("tab_switch", tab_switch))
    app.add_handler(CommandHandler("log", log))

    log("✅ Бот успешно запущен на Railway!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()