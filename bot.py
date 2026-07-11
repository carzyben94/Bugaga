import os
import logging
import json
import subprocess
import time
import requests
import re
import base64
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters, MessageHandler
import websockets

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

AGNES_API_KEY = os.getenv("AGNES_API_KEY")
AGNES_API_URL = os.getenv("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions")

CHROME_PATH = "/usr/bin/google-chrome"

# ---------- Логирование ----------

LOG_FILE = "bot_logs.txt"

class FileLogger:
    def __init__(self, filename=LOG_FILE):
        self.filename = filename
        with open(self.filename, 'w', encoding='utf-8') as f:
            f.write(f"=== Логи бота ===\n")
            f.write(f"Время запуска: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
    
    def log(self, message, level="INFO"):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(self.filename, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")

file_logger = FileLogger()

# ---------- Chrome ----------

def start_chrome():
    try:
        file_logger.log("Запуск Chrome...")
        result = subprocess.run(["pgrep", "-f", "google-chrome"], capture_output=True, text=True)
        if result.stdout:
            file_logger.log("✅ Chrome уже запущен")
            return True
        
        subprocess.Popen([
            CHROME_PATH,
            "--headless=new",
            "--remote-debugging-port=9222",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--user-data-dir=/tmp/chrome-profile",
            "--window-size=1920,1080"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        
        time.sleep(5)
        file_logger.log("✅ Chrome запущен")
        return True
    except Exception as e:
        file_logger.log(f"❌ Ошибка: {e}", "ERROR")
        return False

def get_page_ws_url():
    try:
        response = requests.get("http://localhost:9222/json")
        pages = response.json()
        for page in pages:
            if page.get("type") == "page":
                ws_url = page.get("webSocketDebuggerUrl")
                file_logger.log(f"✅ WebSocket: {ws_url}")
                return ws_url
        return None
    except Exception as e:
        file_logger.log(f"❌ Ошибка: {e}", "ERROR")
        return None

def create_page():
    try:
        response = requests.get("http://localhost:9222/json/new?about:blank")
        data = response.json()
        ws_url = data.get("webSocketDebuggerUrl")
        file_logger.log(f"✅ Создана страница: {ws_url}")
        return ws_url
    except Exception as e:
        file_logger.log(f"❌ Ошибка: {e}", "ERROR")
        return None

# ---------- CDP Client ----------

class CDPClient:
    def __init__(self):
        self.ws = None
        self.connected = False
        self.msg_id = 0
        self.user_id = None
        self.full_snapshot = None
        self.history = []
    
    async def connect(self):
        if self.connected:
            return True
        
        file_logger.log(f"Подключение для пользователя {self.user_id}")
        
        ws_url = get_page_ws_url()
        if not ws_url:
            ws_url = create_page()
        
        if not ws_url:
            file_logger.log("❌ Не удалось получить WebSocket URL", "ERROR")
            return False
        
        try:
            self.ws = await websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=60,
                close_timeout=10
            )
            self.connected = True
            file_logger.log("✅ WebSocket подключен")
            
            await self.send("Page.enable", {})
            await self.send("Runtime.enable", {})
            await self.send("DOM.enable", {})
            file_logger.log("✅ Page, Runtime, DOM включены")
            
            await self.navigate("https://google.com")
            
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Connect error: {e}", "ERROR")
            return False
    
    async def send(self, method, params=None):
        if not self.connected:
            await self.connect()
        
        self.msg_id += 1
        msg_id = self.msg_id
        
        msg = {
            "id": msg_id,
            "method": method,
            "params": params or {}
        }
        
        try:
            await self.ws.send(json.dumps(msg))
            
            while True:
                response = await asyncio.wait_for(self.ws.recv(), timeout=30)
                data = json.loads(response)
                
                if data.get("id") == msg_id:
                    if "error" in data:
                        file_logger.log(f"❌ {method}: {data['error']}", "ERROR")
                    return data
                
                if "method" in data:
                    continue
                
        except asyncio.TimeoutError:
            file_logger.log(f"❌ {method} timeout", "ERROR")
            return {"error": "Timeout"}
        except Exception as e:
            file_logger.log(f"❌ {method} error: {e}", "ERROR")
            return {"error": str(e)}
    
    async def navigate(self, url):
        file_logger.log(f"🌐 Навигация на {url}")
        await self.send("Page.navigate", {"url": url})
        
        for i in range(10):
            await asyncio.sleep(1)
            title = await self.eval_js("document.title")
            if title and title != "":
                file_logger.log(f"📄 Страница загружена: {title}")
                await self.get_maximum_snapshot()
                break
    
    async def eval_js(self, code):
        """Выполняет JavaScript и возвращает результат"""
        try:
            resp = await self.send("Runtime.evaluate", {
                "expression": code,
                "returnByValue": True
            })
            
            if "result" in resp:
                result_obj = resp["result"]
                if "result" in result_obj:
                    return result_obj["result"].get("value", "")
                elif "value" in result_obj:
                    return result_obj["value"]
            return None
        except Exception as e:
            file_logger.log(f"❌ eval_js error: {e}", "ERROR")
            return None
    
    async def get_maximum_snapshot(self):
        """МАКСИМАЛЬНО полный слепок страницы"""
        try:
            file_logger.log("📸 Делаю максимальный слепок...")
            
            # 1. DOM дерево
            dom = await self.send("DOM.getDocument", {
                "depth": -1,
                "pierce": True,
                "includeShadowRoots": True
            })
            
            # 2. Снимок со стилями
            snapshot = await self.send("DOMSnapshot.captureSnapshot", {
                "computedStyles": [
                    "display", "visibility", "position", 
                    "color", "font-size", "background-color",
                    "width", "height", "margin", "padding",
                    "border", "cursor", "pointer-events"
                ],
                "includeDOMRects": True
            })
            
            # 3. ВСЕ элементы с полной информацией
            elements = await self.eval_js("""
                (function() {
                    const result = [];
                    const all = document.querySelectorAll('*');
                    
                    all.forEach(el => {
                        const tag = el.tagName.toLowerCase();
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        
                        const visible = rect.width > 0 && rect.height > 0 && 
                                       style.display !== 'none' && 
                                       style.visibility !== 'hidden';
                        
                        const interactive = ['a', 'button', 'input', 'select', 'textarea'].includes(tag) ||
                                           el.getAttribute('role') === 'button' ||
                                           el.getAttribute('onclick') !== null ||
                                           el.getAttribute('tabindex') !== null;
                        
                        const attrs = {};
                        for (const attr of el.attributes) {
                            attrs[attr.name] = attr.value;
                        }
                        
                        const important = ['a', 'button', 'input', 'textarea', 'select', 'form',
                                          'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'img', 'video',
                                          'iframe', 'div', 'span', 'section', 'article', 'nav',
                                          'header', 'footer', 'main', 'aside', 'ul', 'ol', 'li'];
                        
                        if (important.includes(tag)) {
                            result.push({
                                tag: tag,
                                text: (el.textContent || '').trim().slice(0, 100),
                                id: el.id || '',
                                class: el.className || '',
                                attrs: attrs,
                                visible: visible,
                                interactive: interactive,
                                disabled: el.disabled || false,
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height),
                                style: {
                                    display: style.display,
                                    visibility: style.visibility,
                                    position: style.position,
                                    color: style.color,
                                    fontSize: style.fontSize,
                                    backgroundColor: style.backgroundColor,
                                    cursor: style.cursor,
                                    pointerEvents: style.pointerEvents,
                                    opacity: style.opacity
                                },
                                parent: el.parentElement ? el.parentElement.tagName.toLowerCase() : null,
                                children: el.children.length,
                                hasShadow: el.shadowRoot ? true : false
                            });
                        }
                    });
                    
                    return result;
                })()
            """) or []
            
            title = await self.eval_js("document.title") or "Нет заголовка"
            url = await self.eval_js("window.location.href") or "Нет URL"
            
            self.full_snapshot = {
                "title": title,
                "url": url,
                "total": len(elements),
                "dom": dom,
                "snapshot": snapshot,
                "all_elements": elements[:500],
                "buttons": [e for e in elements if e.get('interactive') and e.get('tag') in ['button', 'a']],
                "inputs": [e for e in elements if e.get('tag') == 'input' and e.get('attrs', {}).get('type') not in ['hidden', 'submit', 'button']],
                "links": [e for e in elements if e.get('tag') == 'a' and e.get('attrs', {}).get('href')],
                "forms": [e for e in elements if e.get('tag') == 'form'],
                "headings": [e for e in elements if e.get('tag') in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']],
                "visible": [e for e in elements if e.get('visible')],
                "interactive": [e for e in elements if e.get('interactive') and e.get('visible')]
            }
            
            file_logger.log(f"✅ Максимальный слепок: {len(elements)} элементов, {len(self.full_snapshot.get('buttons', []))} кнопок, {len(self.full_snapshot.get('inputs', []))} полей")
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Maximum snapshot error: {e}", "ERROR")
            return False
    
    async def get_page_description(self):
        """Возвращает максимальное описание страницы"""
        if not self.full_snapshot:
            await self.get_maximum_snapshot()
        
        info = self.full_snapshot or {}
        
        desc = f"""
📄 **СТРАНИЦА:** {info.get('title', 'Нет заголовка')}
🔗 **URL:** {info.get('url', 'Нет URL')}
📊 **ВСЕГО ЭЛЕМЕНТОВ:** {info.get('total', 0)}

─────────────────────────────────
🔘 **КНОПКИ И ИНТЕРАКТИВНЫЕ ЭЛЕМЕНТЫ ({len(info.get('interactive', []))}):**
"""
        for el in info.get('interactive', [])[:20]:
            text = el.get('text', '') or el.get('attrs', {}).get('value', '')
            tag = el.get('tag', '')
            selector = el.get('id', '') or el.get('class', '') or tag
            if text:
                desc += f"  • {text[:30]} → selector: {selector}\n"
            else:
                desc += f"  • <{tag}> → selector: {selector}\n"
        
        desc += f"\n─────────────────────────────────\n"
        desc += f"📝 **ПОЛЯ ВВОДА ({len(info.get('inputs', []))}):**\n"
        for el in info.get('inputs', [])[:20]:
            attrs = el.get('attrs', {})
            placeholder = attrs.get('placeholder', '')
            name = attrs.get('name', '')
            selector = f"input[name='{name}']" if name else f"input[placeholder='{placeholder}']"
            desc += f"  • {placeholder or name or 'поле'} → selector: {selector}\n"
        
        desc += f"\n─────────────────────────────────\n"
        desc += f"🔗 **ССЫЛКИ ({len(info.get('links', []))}):**\n"
        for el in info.get('links', [])[:15]:
            text = el.get('text', '')[:30]
            href = el.get('attrs', {}).get('href', '')[:50]
            if text:
                desc += f"  • {text} → {href}\n"
        
        desc += f"\n─────────────────────────────────\n"
        desc += f"📋 **ФОРМЫ ({len(info.get('forms', []))}):**\n"
        for el in info.get('forms', [])[:5]:
            action = el.get('attrs', {}).get('action', '')
            method = el.get('attrs', {}).get('method', '')
            desc += f"  • action: {action[:30]}, method: {method}\n"
        
        desc += f"\n─────────────────────────────────\n"
        desc += f"👁️ **ВИДИМЫЕ ЭЛЕМЕНТЫ ({len(info.get('visible', []))}):**\n"
        for el in info.get('visible', [])[:15]:
            tag = el.get('tag', '')
            text = el.get('text', '')[:30]
            if text:
                desc += f"  • <{tag}> {text}\n"
        
        return desc
    
    async def click_element(self, selector):
        js_code = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (el) {{
                el.click();
                return {{ success: true }};
            }}
            return {{ success: false }};
        }})()
        """
        return await self.eval_js(js_code)
    
    async def fill_element(self, selector, value):
        js_code = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (el) {{
                el.value = '{value}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return {{ success: true }};
            }}
            return {{ success: false }};
        }})()
        """
        return await self.eval_js(js_code)
    
    async def press_enter(self):
        js_code = """
        (function() {
            const active = document.activeElement;
            if (active) {
                const event = new KeyboardEvent('keydown', {
                    key: 'Enter',
                    code: 'Enter',
                    keyCode: 13,
                    which: 13,
                    bubbles: true
                });
                active.dispatchEvent(event);
                return { success: true };
            }
            return { success: false };
        })()
        """
        return await self.eval_js(js_code)
    
    async def scroll_to(self, selector):
        js_code = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (el) {{
                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                return {{ success: true }};
            }}
            return {{ success: false }};
        }})()
        """
        return await self.eval_js(js_code)
    
    async def wait_for_element(self, selector, timeout=10):
        js_code = f"""
        (function() {{
            return new Promise((resolve) => {{
                const start = Date.now();
                const check = () => {{
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        resolve({{
                            found: true,
                            selector: '{selector}',
                            text: el.textContent.slice(0, 30)
                        }});
                    }} else if (Date.now() - start > {timeout * 1000}) {{
                        resolve({{ found: false, selector: '{selector}' }});
                    }} else {{
                        setTimeout(check, 200);
                    }}
                }};
                check();
            }});
        }})()
        """
        return await self.eval_js(js_code)
    
    async def get_text(self, selector):
        js_code = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            return el ? el.textContent.trim() : null;
        }})()
        """
        return await self.eval_js(js_code)
    
    async def reload(self):
        await self.send("Page.reload", {})
        await asyncio.sleep(2)
        await self.get_maximum_snapshot()
    
    async def back(self):
        await self.send("Page.goBack", {})
        await asyncio.sleep(2)
        await self.get_maximum_snapshot()
    
    async def forward(self):
        await self.send("Page.goForward", {})
        await asyncio.sleep(2)
        await self.get_maximum_snapshot()
    
    async def screenshot(self):
        try:
            if not self.connected:
                await self.connect()
            
            title = await self.eval_js("document.title")
            file_logger.log(f"📄 Текущий заголовок: {title}")
            
            if not title or title == "":
                file_logger.log("🌐 Открываю Google...")
                await self.navigate("https://google.com")
                await asyncio.sleep(2)
            
            file_logger.log("📸 Делаю скриншот...")
            
            resp = await self.send("Page.captureScreenshot", {
                "format": "png",
                "captureBeyondViewport": True,
                "fromSurface": True
            })
            
            if "result" in resp and "data" in resp["result"]:
                file_logger.log("✅ Скриншот сделан")
                return base64.b64decode(resp["result"]["data"])
            
            return None
                
        except Exception as e:
            file_logger.log(f"❌ Screenshot error: {e}", "ERROR")
            return None

# ---------- Хранилище ----------

clients = {}

# ---------- КОД АГЕНТА ----------

AGENT_CODE = """
🤖 **ТЫ — АГЕНТ ДЛЯ УПРАВЛЕНИЯ БРАУЗЕРОМ**

📌 **ТВОЙ КОД (что ты умеешь делать):**

1. navigate(url) - открыть сайт
2. click(selector) - кликнуть по элементу
3. fill(selector, value) - заполнить поле
4. press_enter() - нажать Enter
5. screenshot() - сделать скриншот
6. answer(text) - ответить пользователю
7. scroll(amount) - прокрутить
8. back() - назад
9. forward() - вперёд
10. reload() - обновить
11. wait_for(selector, timeout) - ждать элемент
12. get_text(selector) - получить текст

📝 **КАК ВЫБИРАТЬ СЕЛЕКТОРЫ:**
- По ID: "#search"
- По классу: ".gLFyf"
- По типу: "input[type='text']"
- По имени: "input[name='q']"
- По тексту: "button:contains('Войти')"
"""

# ---------- Агент ----------

async def ask_agnes(prompt: str, client: CDPClient) -> dict:
    if not AGNES_API_KEY:
        return {"error": "AGNES_API_KEY не установлен"}
    
    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json"
    }
    
    page_desc = await client.get_page_description()
    
    system_prompt = f"""
{AGENT_CODE}

📄 **МАКСИМАЛЬНЫЙ СЛЕПОК СТРАНИЦЫ:**
{page_desc}

📝 **ОТВЕЧАЙ ТОЛЬКО JSON!**
"""

    data = {
        "model": "agnes-2.0-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 500
    }
    
    try:
        response = requests.post(AGNES_API_URL, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        
        file_logger.log(f"Agnes ответ: {content[:200]}...")
        
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {"action": "answer", "params": {"text": content}}
    except Exception as e:
        file_logger.log(f"Agnes error: {e}", "ERROR")
        return {"action": "answer", "params": {"text": f"Ошибка: {str(e)}"}}

# ---------- Выполнение действий ----------

async def execute_action(client: CDPClient, action: dict) -> str:
    action_type = action.get("action")
    params = action.get("params", {})
    
    file_logger.log(f"Выполнение: {action_type}")
    
    try:
        if action_type == "navigate":
            url = params.get("url", "https://google.com")
            await client.navigate(url)
            title = await client.eval_js("document.title")
            return f"✅ Открыл: {url}\n📄 {title}"
        
        elif action_type == "screenshot":
            img_data = await client.screenshot()
            if img_data:
                with open("screenshot.png", "wb") as f:
                    f.write(img_data)
                return "screenshot"
            return "❌ Не удалось сделать скриншот"
        
        elif action_type == "click":
            selector = params.get("selector")
            if not selector:
                return "❌ Нет селектора"
            result = await client.click_element(selector)
            if result and result.get("success"):
                await client.get_maximum_snapshot()
                return f"✅ Кликнул: {selector}"
            return f"❌ Элемент не найден: {selector}"
        
        elif action_type == "fill":
            selector = params.get("selector")
            value = params.get("value", "")
            if not selector:
                return "❌ Нет селектора"
            result = await client.fill_element(selector, value)
            if result and result.get("success"):
                await client.get_maximum_snapshot()
                return f"✅ Заполнил: {selector} = {value}"
            return f"❌ Элемент не найден: {selector}"
        
        elif action_type == "press_enter":
            result = await client.press_enter()
            if result and result.get("success"):
                await client.get_maximum_snapshot()
                return "✅ Нажал Enter"
            return "❌ Не удалось нажать Enter"
        
        elif action_type == "scroll":
            amount = params.get("amount", 500)
            await client.eval_js(f"window.scrollBy(0, {amount})")
            return f"✅ Прокрутил на {amount}px"
        
        elif action_type == "scroll_to":
            selector = params.get("selector")
            if not selector:
                return "❌ Нет селектора"
            result = await client.scroll_to(selector)
            if result and result.get("success"):
                return f"✅ Прокрутил к: {selector}"
            return f"❌ Элемент не найден: {selector}"
        
        elif action_type == "back":
            await client.back()
            return "✅ Назад"
        
        elif action_type == "forward":
            await client.forward()
            return "✅ Вперёд"
        
        elif action_type == "reload":
            await client.reload()
            return "✅ Обновлено"
        
        elif action_type == "wait_for":
            selector = params.get("selector")
            timeout = params.get("timeout", 10)
            if not selector:
                return "❌ Нет селектора"
            result = await client.wait_for_element(selector, timeout)
            if result and result.get("found"):
                return f"✅ Элемент появился: {selector}"
            return f"❌ Элемент не появился: {selector}"
        
        elif action_type == "get_text":
            selector = params.get("selector")
            if not selector:
                return "❌ Нет селектора"
            result = await client.get_text(selector)
            if result:
                return f"📄 Текст:\n{result}"
            return f"❌ Элемент не найден: {selector}"
        
        elif action_type == "answer":
            return f"📝 {params.get('text', 'Нет ответа')}"
        
        else:
            return f"⚠️ Неизвестное действие: {action_type}"
            
    except Exception as e:
        file_logger.log(f"Execute error: {e}", "ERROR")
        return f"❌ Ошибка: {str(e)}"

# ---------- Обработчик ----------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    user_id = update.message.from_user.id
    prompt = update.message.text
    
    file_logger.log(f"Сообщение от {user_id}: {prompt[:100]}...")
    
    await update.message.chat.send_action(action="typing")
    
    try:
        if user_id not in clients:
            client = CDPClient()
            client.user_id = user_id
            await client.connect()
            clients[user_id] = client
        
        client = clients[user_id]
        
        await client.get_maximum_snapshot()
        
        if AGNES_API_KEY:
            response = await ask_agnes(prompt, client)
            if "error" not in response:
                result = await execute_action(client, response)
                if result == "screenshot":
                    with open("screenshot.png", "rb") as photo:
                        await update.message.reply_photo(photo=photo)
                else:
                    await update.message.reply_text(result)
                return
        
        await update.message.reply_text("❌ Не понял команду. Попробуйте переформулировать.")
            
    except Exception as e:
        file_logger.log(f"❌ Ошибка: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ---------- Команды ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 **МАКСИМАЛЬНЫЙ АГЕНТ**\n\n"
        "Я вижу ВСЁ на странице!\n\n"
        "💡 **Примеры команд:**\n"
        "• Открой Google\n"
        "• Нажми на кнопку Войти\n"
        "• Введи в поле текст Привет\n"
        "• Нажми Enter\n"
        "• Что ты видишь?\n"
        "• Сделай скриншот\n\n"
        "/cdp - статус браузера\n"
        "/logs - логи"
    )

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"bot_logs_{time.strftime('%Y-%m-%d_%H-%M-%S')}.txt",
                    caption="📋 Логи бота"
                )
        else:
            await update.message.reply_text("❌ Файл логов не найден")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def clear_logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.write(f"=== Логи очищены ===\n")
            f.write(f"Время очистки: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
        await update.message.reply_text("✅ Логи очищены")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def cdp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        response = requests.get("http://localhost:9222/json")
        pages = response.json()
        
        status_text = f"✅ **Браузер активен**\n\n"
        status_text += f"📄 Страниц: {len(pages)}\n\n"
        
        for page in pages[:3]:
            title = page.get('title', 'без названия')[:30]
            url = page.get('url', '')[:40]
            status_text += f"• {title}\n  {url}\n\n"
        
        await update.message.reply_text(status_text)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ---------- Main ----------

def main():
    print("🚀 Запуск бота...")
    file_logger.log("🚀 Запуск бота...")
    
    start_chrome()
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cdp", cdp))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("clear_logs", clear_logs_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен!")
    file_logger.log("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()