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

# ---------- CDP Client (Супер-агент) ----------

class CDPClient:
    def __init__(self):
        self.ws = None
        self.connected = False
        self.msg_id = 0
        self.user_id = None
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
                break
    
    async def eval_js(self, code):
        resp = await self.send("Runtime.evaluate", {"expression": code})
        if "result" in resp:
            result_obj = resp["result"]
            if isinstance(result_obj, dict):
                if "result" in result_obj:
                    return result_obj["result"].get("value", "")
                elif "value" in result_obj:
                    return result_obj["value"]
        return None
    
    # ---------- DOM методы ----------
    
    async def get_dom_snapshot(self):
        """Получает полный снимок DOM страницы"""
        try:
            snapshot = await self.send("DOMSnapshot.captureSnapshot", {
                "computedStyles": ["display", "visibility", "font-size", "color"],
                "includePaintOrder": False,
                "includeDOMRects": False
            })
            
            if "error" in snapshot:
                return None
            
            dom_doc = await self.send("DOM.getDocument", {
                "depth": -1,
                "pierce": True
            })
            
            if "error" in dom_doc:
                return None
            
            page_info = self._parse_snapshot(snapshot)
            page_info["root_node_id"] = dom_doc.get("root", {}).get("nodeId")
            
            return page_info
            
        except Exception as e:
            file_logger.log(f"❌ DOM snapshot error: {e}", "ERROR")
            return None
    
    def _parse_snapshot(self, snapshot):
        """Парсит DOMSnapshot в читаемый формат"""
        try:
            result = {
                "elements": [],
                "buttons": [],
                "inputs": [],
                "links": [],
                "forms": [],
                "headings": [],
                "text_content": ""
            }
            
            if "documents" not in snapshot or not snapshot["documents"]:
                return result
            
            doc = snapshot["documents"][0]
            nodes = doc.get("nodes", {})
            
            node_names = nodes.get("nodeName", [])
            node_types = nodes.get("nodeType", [])
            node_values = nodes.get("nodeValue", [])
            
            attributes_data = doc.get("attributes", {})
            attr_names = attributes_data.get("name", [])
            attr_values = attributes_data.get("value", [])
            
            for i in range(len(node_names)):
                node_type = node_types[i] if i < len(node_types) else None
                node_name = node_names[i] if i < len(node_names) else ""
                
                if node_type == 3:
                    text = node_values[i] if i < len(node_values) else ""
                    if text and text.strip():
                        result["text_content"] += text + " "
                    continue
                
                if node_type == 1 and node_name:
                    tag = node_name.lower()
                    
                    attrs = {}
                    attr_start = attributes_data.get("startIndex", [])[i] if i < len(attributes_data.get("startIndex", [])) else 0
                    attr_count = attributes_data.get("count", [])[i] if i < len(attributes_data.get("count", [])) else 0
                    
                    for j in range(attr_start, attr_start + attr_count):
                        if j < len(attr_names) and j < len(attr_values):
                            attrs[attr_names[j]] = attr_values[j]
                    
                    element_info = {
                        "tag": tag,
                        "attributes": attrs,
                        "text": attrs.get("text", "") or attrs.get("value", "") or attrs.get("placeholder", "")
                    }
                    
                    result["elements"].append(element_info)
                    
                    if tag in ["button", "input[type='submit']"]:
                        result["buttons"].append(element_info)
                    elif tag == "input":
                        result["inputs"].append(element_info)
                    elif tag == "a":
                        result["links"].append(element_info)
                    elif tag == "form":
                        result["forms"].append(element_info)
                    elif tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                        result["headings"].append(element_info)
            
            return result
            
        except Exception as e:
            file_logger.log(f"❌ Parse snapshot error: {e}", "ERROR")
            return {"error": str(e)}
    
    # ---------- Расширенные методы ----------
    
    async def get_interactive_elements(self):
        """Находит все интерактивные элементы"""
        js_code = """
        (function() {
            const interactive = [];
            const selectors = [
                'button',
                'a[href]',
                'input[type="submit"]',
                'input[type="button"]',
                '[role="button"]',
                '[onclick]',
                '[tabindex]:not([tabindex="-1"])',
                '[contenteditable="true"]'
            ];
            
            document.querySelectorAll(selectors.join(',')).forEach(el => {
                const rect = el.getBoundingClientRect();
                const visible = rect.width > 0 && rect.height > 0 && 
                               el.offsetParent !== null;
                
                if (visible) {
                    interactive.push({
                        tag: el.tagName,
                        text: (el.textContent || el.value || '').slice(0, 30),
                        id: el.id || '',
                        class: el.className || '',
                        type: el.type || '',
                        href: el.href || '',
                        selector: el.id ? '#' + el.id : 
                                  el.className ? '.' + el.className.split(' ').join('.') : 
                                  el.tagName
                    });
                }
            });
            
            return interactive.slice(0, 20);
        })()
        """
        return await self.eval_js(js_code)
    
    async def get_visible_elements(self):
        """Получает все видимые элементы"""
        js_code = """
        (function() {
            const visible = [];
            const all = document.querySelectorAll('*');
            
            all.forEach(el => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                
                if (rect.width > 0 && rect.height > 0 && 
                    style.display !== 'none' && 
                    style.visibility !== 'hidden' &&
                    el.offsetParent !== null) {
                    
                    const tag = el.tagName.toLowerCase();
                    const text = (el.textContent || '').trim().slice(0, 30);
                    
                    if (['button', 'a', 'input', 'textarea', 'select', 'h1', 'h2', 'h3', 'p', 'div'].includes(tag)) {
                        visible.push({
                            tag: tag,
                            text: text,
                            id: el.id || '',
                            class: el.className || '',
                            selector: el.id ? '#' + el.id : 
                                      el.className ? '.' + el.className.split(' ').join('.') : 
                                      tag
                        });
                    }
                }
            });
            
            return visible.slice(0, 30);
        })()
        """
        return await self.eval_js(js_code)
    
    async def get_element_visibility(self, selector):
        """Проверяет, виден ли элемент"""
        js_code = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (!el) return null;
            
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            
            return {{
                visible: el.offsetParent !== null && 
                         style.display !== 'none' && 
                         style.visibility !== 'hidden' &&
                         rect.width > 0 && rect.height > 0,
                inViewport: rect.top < window.innerHeight && 
                            rect.bottom > 0,
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height
            }};
        }})()
        """
        return await self.eval_js(js_code)
    
    async def wait_for_element(self, selector, timeout=10):
        """Ждёт появления элемента"""
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
    
    async def scroll_to_element(self, selector):
        """Скроллит к элементу"""
        js_code = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (el) {{
                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                return {{ success: true, selector: '{selector}' }};
            }}
            return {{ success: false, selector: '{selector}' }};
        }})()
        """
        return await self.eval_js(js_code)
    
    async def get_text_content(self, selector):
        """Получает текст элемента"""
        js_code = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (!el) return null;
            
            return {{
                text: el.textContent.trim(),
                innerHTML: el.innerHTML.slice(0, 500),
                outerHTML: el.outerHTML.slice(0, 500)
            }};
        }})()
        """
        return await self.eval_js(js_code)
    
    async def get_page_state(self):
        """Полное состояние страницы"""
        return {
            "url": await self.eval_js("window.location.href"),
            "title": await self.eval_js("document.title"),
            "scrollY": await self.eval_js("window.scrollY"),
            "scrollHeight": await self.eval_js("document.body.scrollHeight"),
            "viewportHeight": await self.eval_js("window.innerHeight"),
            "interactive": await self.get_interactive_elements(),
            "visible": await self.get_visible_elements()
        }
    
    async def click_element(self, selector):
        """Кликает по элементу"""
        js_code = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (el) {{
                el.click();
                return {{ success: true, selector: '{selector}' }};
            }}
            return {{ success: false, selector: '{selector}' }};
        }})()
        """
        return await self.eval_js(js_code)
    
    async def fill_element(self, selector, value):
        """Заполняет поле ввода"""
        js_code = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (el) {{
                el.value = '{value}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return {{ success: true, selector: '{selector}', value: '{value}' }};
            }}
            return {{ success: false, selector: '{selector}' }};
        }})()
        """
        return await self.eval_js(js_code)
    
    async def wait_for_and_click(self, selector, timeout=10):
        """Ждёт элемент и кликает по нему"""
        wait_result = await self.wait_for_element(selector, timeout)
        if wait_result.get("found"):
            return await self.click_element(selector)
        return {"error": "Element not found", "selector": selector}
    
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

# ---------- Agnes AI с полным DOM доступом ----------

async def ask_agnes(prompt: str, client: CDPClient = None) -> dict:
    if not AGNES_API_KEY:
        return {"error": "AGNES_API_KEY не установлен"}
    
    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json"
    }
    
    dom_info = "Страница не загружена"
    if client:
        try:
            snapshot = await client.get_dom_snapshot()
            interactive = await client.get_interactive_elements()
            visible = await client.get_visible_elements()
            
            if snapshot and not snapshot.get("error"):
                dom_info = f"""
📄 **ПОЛНАЯ СТРУКТУРА СТРАНИЦЫ:**

🔘 **КНОПКИ ({len(snapshot.get('buttons', []))}):**
{json.dumps(snapshot.get('buttons', [])[:10], indent=2, ensure_ascii=False)}

📝 **ПОЛЯ ВВОДА ({len(snapshot.get('inputs', []))}):**
{json.dumps(snapshot.get('inputs', [])[:10], indent=2, ensure_ascii=False)}

🔗 **ССЫЛКИ ({len(snapshot.get('links', []))}):**
{json.dumps(snapshot.get('links', [])[:10], indent=2, ensure_ascii=False)}

🖱️ **ИНТЕРАКТИВНЫЕ ЭЛЕМЕНТЫ ({len(interactive)}):**
{json.dumps(interactive[:10], indent=2, ensure_ascii=False)}

👁️ **ВИДИМЫЕ ЭЛЕМЕНТЫ ({len(visible)}):**
{json.dumps(visible[:10], indent=2, ensure_ascii=False)}

📊 **ВСЕГО ЭЛЕМЕНТОВ: {len(snapshot.get('elements', []))}**

💡 **Что видно на странице:**
- Кнопки: {[b.get('text') for b in snapshot.get('buttons', [])[:5]]}
- Поля: {[i.get('text') for i in snapshot.get('inputs', [])[:5]]}
- Ссылки: {[l.get('text') for l in snapshot.get('links', [])[:5]]}
- Интерактивные: {[i.get('text') for i in interactive[:5]]}
"""
        except Exception as e:
            dom_info = f"Ошибка получения DOM: {e}"
    
    system_prompt = f"""
Ты AI-агент для управления браузером через CDP.

{dom_info}

📌 **Доступные действия (отвечай ТОЛЬКО JSON):**
1. navigate — перейти на URL
2. screenshot — сделать скриншот
3. click — кликнуть по элементу
4. fill — заполнить поле
5. scroll — прокрутить
6. wait — ждать элемент
7. js — выполнить код
8. get_text — получить текст

🎯 **Как выбирать селекторы:**
- По ID: "button#submit"
- По классу: ".btn-primary"
- По типу: "input[type='email']"
- По тексту: "button:contains('Войти')"

📝 **Отвечай ТОЛЬКО JSON!**
Пример: {{"action": "click", "params": {{"selector": "button"}}}}
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
        
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {"action": "js", "params": {"code": "document.title"}}
    except Exception as e:
        file_logger.log(f"Agnes error: {e}", "ERROR")
        return {"error": str(e)}

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
            result = await client.click_element(selector)
            if result.get("success"):
                return f"✅ Кликнул: {selector}"
            return f"❌ Элемент не найден: {selector}"
        
        elif action_type == "fill":
            selector = params.get("selector")
            value = params.get("value", "")
            result = await client.fill_element(selector, value)
            if result.get("success"):
                return f"✅ Заполнил: {selector} = {value}"
            return f"❌ Элемент не найден: {selector}"
        
        elif action_type == "scroll":
            selector = params.get("selector")
            if selector:
                result = await client.scroll_to_element(selector)
                if result.get("success"):
                    return f"✅ Прокрутил к: {selector}"
                return f"❌ Элемент не найден: {selector}"
            amount = params.get("amount", 500)
            await client.eval_js(f"window.scrollBy(0, {amount})")
            return f"✅ Прокрутил на {amount}px"
        
        elif action_type == "wait":
            selector = params.get("selector")
            timeout = params.get("timeout", 10)
            result = await client.wait_for_element(selector, timeout)
            if result.get("found"):
                return f"✅ Элемент появился: {selector}"
            return f"❌ Элемент не появился: {selector}"
        
        elif action_type == "get_text":
            selector = params.get("selector")
            result = await client.get_text_content(selector)
            if result:
                return f"📄 Текст:\n{result.get('text', 'Нет текста')}"
            return f"❌ Элемент не найден: {selector}"
        
        elif action_type == "js":
            code = params.get("code", "document.title")
            result = await client.eval_js(code)
            return f"✅ Результат: {result}"
        
        else:
            return f"⚠️ Неизвестное действие: {action_type}"
            
    except Exception as e:
        file_logger.log(f"Execute error: {e}", "ERROR")
        return f"❌ Ошибка: {str(e)}"

# ---------- Прямые команды ----------

async def execute_command(client: CDPClient, command: str) -> str:
    cmd = command.lower()
    
    if any(x in cmd for x in ["google", "гугл"]):
        await client.navigate("https://google.com")
        title = await client.eval_js("document.title")
        return f"✅ Открыл Google\n📄 {title}"
    
    if any(x in cmd for x in ["ютуб", "youtube"]):
        await client.navigate("https://youtube.com")
        title = await client.eval_js("document.title")
        return f"✅ Открыл YouTube\n📄 {title}"
    
    if any(x in cmd for x in ["скриншот", "скрин", "screenshot"]):
        img_data = await client.screenshot()
        if img_data:
            with open("screenshot.png", "wb") as f:
                f.write(img_data)
            return "screenshot"
        return "❌ Не удалось сделать скриншот"
    
    if command.startswith("http"):
        await client.navigate(command)
        title = await client.eval_js("document.title")
        return f"✅ Открыл\n📄 {title}"
    
    return None

# ---------- Команды ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Супер-агент для управления браузером**\n\n"
        "Я вижу ВСЁ на странице! Просто скажи что сделать.\n\n"
        "📌 **Что я умею:**\n"
        "• Открывать сайты\n"
        "• Кликать по кнопкам\n"
        "• Заполнять формы\n"
        "• Делать скриншоты\n"
        "• Прокручивать страницу\n"
        "• Ждать загрузки элементов\n"
        "• Читать текст\n\n"
        "💡 **Примеры:**\n"
        "• Открой Google\n"
        "• Нажми на кнопку Войти\n"
        "• Заполни поле email\n"
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
        
        # Сначала пробуем прямые команды
        result = await execute_command(client, prompt)
        if result:
            if result == "screenshot":
                with open("screenshot.png", "rb") as photo:
                    await update.message.reply_photo(photo=photo)
            else:
                await update.message.reply_text(result)
            return
        
        # Если не распознали - спрашиваем Agnes
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