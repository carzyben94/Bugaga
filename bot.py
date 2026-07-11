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
        self.page_structure = None
        self.tabs = {}
        self.active_tab = None
        self.network_enabled = False
        self.console_messages = []
        self.cookies = []
        self.websocket_messages = []
        self.dialog_messages = []
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
            
            # Включаем все домены для полного контроля
            await self.send("Page.enable", {})
            await self.send("Runtime.enable", {})
            await self.send("DOM.enable", {})
            await self.send("Network.enable", {})
            await self.send("Emulation.enable", {})
            await self.send("Input.enable", {})
            await self.send("Browser.enable", {})
            await self.send("Target.enable", {})
            file_logger.log("✅ Все домены включены")
            
            await self.navigate("https://google.com")
            await self.update_page_structure()
            
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
                
                # Обрабатываем события
                if "method" in data:
                    await self._handle_event(data)
                    continue
                
        except asyncio.TimeoutError:
            file_logger.log(f"❌ {method} timeout", "ERROR")
            return {"error": "Timeout"}
        except Exception as e:
            file_logger.log(f"❌ {method} error: {e}", "ERROR")
            return {"error": str(e)}
    
    async def _handle_event(self, event):
        """Обрабатывает события от браузера"""
        method = event.get("method")
        params = event.get("params", {})
        
        if method == "Runtime.consoleAPICalled":
            self.console_messages.append(params)
            file_logger.log(f"📝 Консоль: {params}")
        
        elif method == "Network.requestWillBeSent":
            file_logger.log(f"🌐 Запрос: {params.get('request', {}).get('url')}")
        
        elif method == "Page.javascriptDialogOpening":
            self.dialog_messages.append(params)
            file_logger.log(f"💬 Диалог: {params}")
    
    async def navigate(self, url):
        file_logger.log(f"🌐 Навигация на {url}")
        await self.send("Page.navigate", {"url": url})
        
        for i in range(10):
            await asyncio.sleep(1)
            title = await self.eval_js("document.title")
            if title and title != "":
                file_logger.log(f"📄 Страница загружена: {title}")
                await self.update_page_structure()
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
    
    async def update_page_structure(self):
        """Обновляет полную структуру страницы с проникновением в iframe и shadow DOM"""
        try:
            file_logger.log("🔄 Обновляю структуру страницы...")
            
            # Получаем ВСЕ элементы с проникновением в iframe и shadow DOM
            elements = await self.eval_js("""
                (function() {
                    const all = document.querySelectorAll('*');
                    const result = [];
                    
                    all.forEach(el => {
                        const tag = el.tagName.toLowerCase();
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        
                        // Собираем все атрибуты
                        const attrs = {};
                        for (const attr of el.attributes) {
                            attrs[attr.name] = attr.value;
                        }
                        
                        // Проверяем видимость
                        const visible = rect.width > 0 && rect.height > 0 && 
                                       style.display !== 'none' && 
                                       style.visibility !== 'hidden';
                        
                        // Все значимые элементы
                        const important = ['a', 'button', 'input', 'textarea', 'select', 'form',
                                          'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'img', 'video',
                                          'iframe', 'div', 'span', 'section', 'article', 'nav',
                                          'header', 'footer', 'main', 'aside', 'ul', 'ol', 'li',
                                          'table', 'tr', 'td', 'th', 'label', 'option', 'legend',
                                          'fieldset', 'dialog', 'details', 'summary', 'figure',
                                          'figcaption', 'time', 'mark', 'ruby', 'rt', 'rp'];
                        
                        if (important.includes(tag)) {
                            result.push({
                                tag: tag,
                                text: (el.textContent || '').trim().slice(0, 100),
                                id: el.id || '',
                                class: el.className || '',
                                attrs: attrs,
                                visible: visible,
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height)
                            });
                        }
                    });
                    
                    return result;
                })()
            """)
            
            # Сохраняем структуру
            self.page_structure = {
                "title": await self.eval_js("document.title"),
                "url": await self.eval_js("window.location.href"),
                "total": len(elements) if elements else 0,
                "elements": elements[:100] if elements else [],
                "buttons": [e for e in elements if e.get('tag') in ['button'] or (e.get('tag') == 'input' and e.get('attrs', {}).get('type') in ['submit', 'button'])],
                "inputs": [e for e in elements if e.get('tag') == 'input' and e.get('attrs', {}).get('type') not in ['hidden', 'submit', 'button']],
                "links": [e for e in elements if e.get('tag') == 'a' and e.get('attrs', {}).get('href')],
                "forms": [e for e in elements if e.get('tag') == 'form'],
                "headings": [e for e in elements if e.get('tag') in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']],
                "visible": [e for e in elements if e.get('visible')],
                "images": [e for e in elements if e.get('tag') == 'img'],
                "videos": [e for e in elements if e.get('tag') == 'video'],
                "iframes": [e for e in elements if e.get('tag') == 'iframe']
            }
            
            file_logger.log(f"✅ Структура обновлена: {len(elements)} элементов")
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Структура ошибка: {e}", "ERROR")
            self.page_structure = {"error": str(e)}
            return False
    
    async def get_page_description(self):
        """Возвращает текстовое описание страницы"""
        if not self.page_structure:
            await self.update_page_structure()
        
        structure = self.page_structure or {}
        
        description = f"""
📄 **СТРАНИЦА:** {structure.get('title', 'Нет заголовка')}
🔗 **URL:** {structure.get('url', 'Нет URL')}
📊 **ВСЕГО ЭЛЕМЕНТОВ:** {structure.get('total', 0)}

🔘 **КНОПКИ ({len(structure.get('buttons', []))}):**
"""
        for b in structure.get('buttons', [])[:10]:
            text = b.get('text', '') or b.get('attrs', {}).get('value', '')
            if text:
                description += f"  • {text[:30]}\n"
        
        description += f"\n📝 **ПОЛЯ ВВОДА ({len(structure.get('inputs', []))}):\n"
        for inp in structure.get('inputs', [])[:10]:
            placeholder = inp.get('attrs', {}).get('placeholder', '')
            if placeholder:
                description += f"  • {placeholder}\n"
        
        description += f"\n🔗 **ССЫЛКИ ({len(structure.get('links', []))}):\n"
        for link in structure.get('links', [])[:10]:
            text = link.get('text', '')[:30]
            if text:
                description += f"  • {text}\n"
        
        description += f"\n👁️ **ВИДИМЫЕ ЭЛЕМЕНТЫ ({len(structure.get('visible', []))}):\n"
        for el in structure.get('visible', [])[:10]:
            tag = el.get('tag', '')
            text = el.get('text', '')[:30]
            if text:
                description += f"  • <{tag}> {text}\n"
        
        return description
    
    # ---------- ВЗАИМОДЕЙСТВИЕ С ЭЛЕМЕНТАМИ ----------
    
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
    
    async def double_click(self, selector):
        js_code = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (el) {{
                const event = new MouseEvent('dblclick', {{
                    view: window,
                    bubbles: true,
                    cancelable: true
                }});
                el.dispatchEvent(event);
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
    
    async def select_option(self, selector, value):
        js_code = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (el) {{
                el.value = '{value}';
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return {{ success: true }};
            }}
            return {{ success: false }};
        }})()
        """
        return await self.eval_js(js_code)
    
    async def set_checkbox(self, selector, checked=True):
        js_code = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (el) {{
                el.checked = {str(checked).lower()};
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return {{ success: true }};
            }}
            return {{ success: false }};
        }})()
        """
        return await self.eval_js(js_code)
    
    # ---------- РАБОТА С СЕТЬЮ ----------
    
    async def enable_network_monitoring(self):
        """Включает мониторинг сети"""
        await self.send("Network.enable", {})
        self.network_enabled = True
        file_logger.log("✅ Мониторинг сети включен")
    
    async def get_cookies(self):
        resp = await self.send("Network.getAllCookies", {})
        return resp.get("result", {}).get("cookies", [])
    
    async def set_cookie(self, name, value, domain=None, path="/"):
        params = {"name": name, "value": value, "path": path}
        if domain:
            params["domain"] = domain
        return await self.send("Network.setCookie", params)
    
    async def block_images(self):
        await self.send("Network.setBlockedURLs", {
            "urls": ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp"]
        })
        file_logger.log("✅ Картинки заблокированы")
    
    # ---------- ЭМУЛЯЦИЯ ----------
    
    async def emulate_device(self, device="mobile"):
        devices = {
            "mobile": {"width": 375, "height": 812, "deviceScaleFactor": 2, "mobile": True},
            "tablet": {"width": 768, "height": 1024, "deviceScaleFactor": 1.5, "mobile": True},
            "desktop": {"width": 1920, "height": 1080, "deviceScaleFactor": 1, "mobile": False}
        }
        
        if device in devices:
            params = devices[device]
            await self.send("Emulation.setDeviceMetricsOverride", params)
            file_logger.log(f"✅ Эмулирую устройство: {device}")
            return True
        return False
    
    async def emulate_geolocation(self, lat, lon, accuracy=100):
        await self.send("Emulation.setGeolocationOverride", {
            "latitude": lat,
            "longitude": lon,
            "accuracy": accuracy
        })
        file_logger.log(f"✅ Геолокация: {lat}, {lon}")
    
    # ---------- РАБОТА С КОНСОЛЬЮ ----------
    
    async def get_console_logs(self):
        return self.console_messages
    
    async def clear_console(self):
        self.console_messages = []
        file_logger.log("✅ Консоль очищена")
    
    # ---------- ДИАЛОГИ ----------
    
    async def handle_dialog(self, accept=True, prompt_text=""):
        return await self.send("Page.handleJavaScriptDialog", {
            "accept": accept,
            "promptText": prompt_text
        })
    
    # ---------- ВКЛАДКИ ----------
    
    async def create_tab(self, url="about:blank"):
        resp = await self.send("Target.createTarget", {"url": url})
        if "result" in resp:
            target_id = resp["result"]["targetId"]
            self.tabs[target_id] = {"id": target_id}
            self.active_tab = target_id
            
            resp = await self.send("Target.attachToTarget", {"targetId": target_id})
            if "result" in resp:
                session_id = resp["result"]["sessionId"]
                self.tabs[target_id]["session_id"] = session_id
                file_logger.log(f"✅ Новая вкладка: {target_id}")
                return target_id
        return None
    
    async def switch_tab(self, target_id):
        if target_id in self.tabs:
            self.active_tab = target_id
            file_logger.log(f"✅ Переключил на вкладку: {target_id}")
            return True
        return False
    
    async def close_tab(self, target_id):
        await self.send("Target.closeTarget", {"targetId": target_id})
        if target_id in self.tabs:
            del self.tabs[target_id]
            if self.active_tab == target_id:
                self.active_tab = list(self.tabs.keys())[0] if self.tabs else None
            file_logger.log(f"✅ Вкладка закрыта: {target_id}")
            return True
        return False
    
    # ---------- СКРИНШОТ ----------
    
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

# ---------- Agnes AI с полным доступом ----------

async def ask_agnes(prompt: str, client: CDPClient = None) -> dict:
    if not AGNES_API_KEY:
        return {"error": "AGNES_API_KEY не установлен"}
    
    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Получаем описание страницы
    page_desc = "Страница не загружена"
    if client and client.page_structure:
        page_desc = await client.get_page_description()
    
    system_prompt = f"""
Ты AI-агент для управления браузером. Отвечай ТОЛЬКО JSON.

{page_desc}

📌 **ДОСТУПНЫЕ ДЕЙСТВИЯ:**
1. navigate - перейти на URL
2. screenshot - скриншот
3. click - кликнуть
4. fill - заполнить поле
5. scroll - прокрутить
6. wait - ждать элемент
7. get_text - получить текст
8. back - назад
9. forward - вперёд
10. reload - обновить
11. new_tab - новая вкладка
12. close_tab - закрыть вкладку
13. get_cookies - получить куки
14. set_cookie - установить куки
15. block_images - блокировать картинки
16. emulate_device - эмулировать устройство
17. get_console - получить логи консоли

🎯 **СЕЛЕКТОРЫ (из того что видно на странице):**
"""
    if client and client.page_structure:
        for el in client.page_structure.get('visible', [])[:10]:
            tag = el.get('tag', '')
            text = el.get('text', '')[:30]
            if text:
                system_prompt += f"- {tag}: '{text}' → selector: {el.get('id', '') or el.get('class', '') or tag}\n"
    
    system_prompt += """
📝 **ПРИМЕРЫ ОТВЕТОВ:**
- {"action": "click", "params": {"selector": "button"}}
- {"action": "fill", "params": {"selector": "input", "value": "текст"}}
- {"action": "screenshot", "params": {}}
- {"action": "answer", "params": {"text": "На странице Google есть поле поиска"}}

📝 **Отвечай ТОЛЬКО JSON!**
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
        
        file_logger.log(f"Agnes: {content[:200]}...")
        
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
            await client.update_page_structure()
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
                await client.update_page_structure()
                return f"✅ Кликнул: {selector}"
            return f"❌ Элемент не найден: {selector}"
        
        elif action_type == "fill":
            selector = params.get("selector")
            value = params.get("value", "")
            if not selector:
                return "❌ Нет селектора"
            result = await client.fill_element(selector, value)
            if result and result.get("success"):
                await client.update_page_structure()
                return f"✅ Заполнил: {selector} = {value}"
            return f"❌ Элемент не найден: {selector}"
        
        elif action_type == "scroll":
            selector = params.get("selector")
            if selector:
                result = await client.scroll_to(selector)
                if result and result.get("success"):
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
            result = await client.get_text(selector)
            if result:
                return f"📄 Текст:\n{result}"
            return f"❌ Элемент не найден: {selector}"
        
        elif action_type == "back":
            await client.send("Page.goBack", {})
            await client.update_page_structure()
            return "✅ Назад"
        
        elif action_type == "forward":
            await client.send("Page.goForward", {})
            await client.update_page_structure()
            return "✅ Вперёд"
        
        elif action_type == "reload":
            await client.send("Page.reload", {})
            await client.update_page_structure()
            return "✅ Обновлено"
        
        elif action_type == "new_tab":
            url = params.get("url", "about:blank")
            tab_id = await client.create_tab(url)
            if tab_id:
                return f"✅ Новая вкладка: {tab_id[:8]}"
            return "❌ Не удалось создать вкладку"
        
        elif action_type == "close_tab":
            tab_id = params.get("tab_id")
            if tab_id:
                result = await client.close_tab(tab_id)
                if result:
                    return f"✅ Вкладка закрыта"
            return "❌ Не удалось закрыть вкладку"
        
        elif action_type == "block_images":
            await client.block_images()
            return "✅ Картинки заблокированы"
        
        elif action_type == "emulate_device":
            device = params.get("device", "mobile")
            result = await client.emulate_device(device)
            if result:
                return f"✅ Эмулирую: {device}"
            return "❌ Неизвестное устройство"
        
        elif action_type == "get_cookies":
            cookies = await client.get_cookies()
            return f"🍪 Куки:\n{json.dumps(cookies, indent=2, ensure_ascii=False)[:500]}"
        
        elif action_type == "set_cookie":
            name = params.get("name")
            value = params.get("value")
            if name and value:
                await client.set_cookie(name, value)
                return f"✅ Кука установлена: {name}={value}"
            return "❌ Нет имени или значения"
        
        elif action_type == "answer":
            return f"📝 {params.get('text', 'Нет ответа')}"
        
        elif action_type == "js":
            code = params.get("code", "document.title")
            result = await client.eval_js(code)
            return f"✅ Результат: {result}"
        
        else:
            return f"⚠️ Неизвестно: {action_type}"
            
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
        
        # Спрашиваем Agnes
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
        "🤖 **СУПЕР-АГЕНТ для управления браузером**\n\n"
        "Я вижу ВСЁ на странице и могу ВСЕМ управлять!\n\n"
        "📌 **Что я умею:**\n"
        "• Вижу все кнопки, поля, ссылки\n"
        "• Кликаю, заполняю, прокручиваю\n"
        "• Открываю новые вкладки\n"
        "• Эмулирую мобильные устройства\n"
        "• Работаю с куками и консолью\n"
        "• Блокирую картинки\n"
        "• Делаю скриншоты\n\n"
        "💡 **Примеры команд:**\n"
        "• Что ты видишь?\n"
        "• Открой Google\n"
        "• Нажми на кнопку Войти\n"
        "• Заполни поле поиска\n"
        "• Сделай скриншот\n"
        "• Эмулируй мобильное устройство\n\n"
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