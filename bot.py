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
        self.page_info = None
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
                await self.update_page_info()
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
    
    async def update_page_info(self):
        """Получает информацию о странице"""
        try:
            elements = await self.eval_js("""
                (function() {
                    const result = {
                        buttons: [],
                        inputs: [],
                        links: [],
                        forms: [],
                        headings: []
                    };
                    
                    document.querySelectorAll('button').forEach(el => {
                        const text = el.textContent.trim();
                        if (text) result.buttons.push(text.slice(0, 30));
                    });
                    
                    document.querySelectorAll('input[type="submit"], input[type="button"]').forEach(el => {
                        const text = el.value || el.placeholder || '';
                        if (text) result.buttons.push(text.slice(0, 30));
                    });
                    
                    document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"])').forEach(el => {
                        const text = el.placeholder || el.name || el.type || '';
                        if (text) result.inputs.push(text.slice(0, 30));
                    });
                    
                    document.querySelectorAll('textarea').forEach(el => {
                        const text = el.placeholder || el.name || '';
                        if (text) result.inputs.push(text.slice(0, 30));
                    });
                    
                    document.querySelectorAll('a[href]').forEach(el => {
                        const text = el.textContent.trim();
                        if (text) result.links.push(text.slice(0, 30));
                    });
                    
                    document.querySelectorAll('form').forEach(el => {
                        result.forms.push(el.action || el.method || 'form');
                    });
                    
                    document.querySelectorAll('h1, h2, h3').forEach(el => {
                        const text = el.textContent.trim();
                        if (text) result.headings.push(text.slice(0, 30));
                    });
                    
                    return result;
                })()
            """)
            
            self.page_info = {
                "title": await self.eval_js("document.title"),
                "url": await self.eval_js("window.location.href"),
                "buttons": elements.get("buttons", []),
                "inputs": elements.get("inputs", []),
                "links": elements.get("links", []),
                "forms": elements.get("forms", []),
                "headings": elements.get("headings", [])
            }
            
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Update info error: {e}", "ERROR")
            return False
    
    async def get_page_description(self):
        if not self.page_info:
            await self.update_page_info()
        
        info = self.page_info or {}
        
        desc = f"""
📄 **СТРАНИЦА:** {info.get('title', 'Нет заголовка')}
🔗 **URL:** {info.get('url', 'Нет URL')}

🔘 **КНОПКИ:**
{chr(10).join(f'  • {btn}' for btn in info.get('buttons', [])[:10])}

📝 **ПОЛЯ ВВОДА:**
{chr(10).join(f'  • {inp}' for inp in info.get('inputs', [])[:10])}

🔗 **ССЫЛКИ:**
{chr(10).join(f'  • {link}' for link in info.get('links', [])[:10])}

📋 **ФОРМЫ:**
{chr(10).join(f'  • {form}' for form in info.get('forms', [])[:5])}

📑 **ЗАГОЛОВКИ:**
{chr(10).join(f'  • {h}' for h in info.get('headings', [])[:5])}
"""
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
    
    async def back(self):
        return await self.send("Page.goBack", {})
    
    async def forward(self):
        return await self.send("Page.goForward", {})
    
    async def reload(self):
        return await self.send("Page.reload", {})

# ---------- Хранилище ----------

clients = {}

# ---------- КОД, КОТОРЫЙ ВИДИТ АГЕНТ ----------

AGENT_CODE = """
🤖 **МОЙ КОД - что я могу делать:**

📌 **ДОСТУПНЫЕ ФУНКЦИИ:**

1. navigate(url)
   - Описание: Открыть сайт
   - Пример: navigate("https://google.com")
   - Где взять URL: из команды пользователя

2. click(selector)
   - Описание: Кликнуть по элементу
   - Пример: click("button:contains('Войти')")
   - Как найти selector: 
     - По тексту: "button:contains('Текст')"
     - По ID: "#login-btn"
     - По классу: ".btn-primary"
     - По типу: "input[type='text']"
     - По placeholder: "input[placeholder='Поиск']"

3. fill(selector, value)
   - Описание: Заполнить поле
   - Пример: fill("input[placeholder='Поиск']", "Привет")
   - Как найти selector: смотри выше

4. screenshot()
   - Описание: Сделать скриншот
   - Пример: screenshot()

5. get_text(selector)
   - Описание: Получить текст элемента
   - Пример: get_text("h1")
   - Возвращает: текст элемента

6. answer(text)
   - Описание: Ответить пользователю
   - Пример: answer("На странице есть кнопка 'Войти'")

7. scroll(amount)
   - Описание: Прокрутить страницу
   - Пример: scroll(500)

8. scroll_to(selector)
   - Описание: Прокрутить к элементу
   - Пример: scroll_to("#form")

9. back()
   - Описание: Назад по истории
   - Пример: back()

10. forward()
    - Описание: Вперёд по истории
    - Пример: forward()

11. reload()
    - Описание: Обновить страницу
    - Пример: reload()

12. wait_for(selector, timeout=10)
    - Описание: Ждать появления элемента
    - Пример: wait_for("button", 10)

📊 **ЧТО СЕЙЧАС НА СТРАНИЦЕ:**
🔘 Кнопки: {buttons}
📝 Поля: {inputs}
🔗 Ссылки: {links}
📋 Формы: {forms}
📑 Заголовки: {headings}

⚠️ **КАК ИСПОЛЬЗОВАТЬ:**
1. Посмотри на страницу
2. Выбери нужную функцию
3. Подставь правильные параметры
4. Выполни

📝 **ПРИМЕРЫ РАБОТЫ:**
- Пользователь: "Открой Google"
  → Я: navigate("https://google.com")

- Пользователь: "Нажми на кнопку Войти"
  → Я: click("button:contains('Войти')")

- Пользователь: "Что видишь?"
  → Я: answer("На странице Google есть поле поиска и кнопка 'Поиск в Google'")

- Пользователь: "Введи в поле текст Привет"
  → Я: fill("input[placeholder='Поиск']", "Привет")

- Пользователь: "Сделай скриншот"
  → Я: screenshot()

- Пользователь: "Прокрути вниз"
  → Я: scroll(500)

🚀 **ГОТОВ К РАБОТЕ!**
"""

# ---------- Агент с видимостью кода ----------

async def ask_agnes_with_code(prompt: str, client: CDPClient) -> dict:
    """Агент видит свой код"""
    
    if not AGNES_API_KEY:
        return {"error": "AGNES_API_KEY не установлен"}
    
    # Получаем информацию о странице
    if client and client.page_info:
        info = client.page_info
        buttons = info.get('buttons', [])
        inputs = info.get('inputs', [])
        links = info.get('links', [])
        forms = info.get('forms', [])
        headings = info.get('headings', [])
    else:
        buttons = inputs = links = forms = headings = []
    
    # Формируем полный промпт с кодом
    system_prompt = f"""
Ты — ИИ-агент, который управляет браузером через CDP.

ВОТ ТВОЙ КОД (что ты умеешь делать):
{AGENT_CODE.format(
    buttons=buttons[:10] if buttons else 'Нет данных',
    inputs=inputs[:10] if inputs else 'Нет данных',
    links=links[:10] if links else 'Нет данных',
    forms=forms[:5] if forms else 'Нет данных',
    headings=headings[:5] if headings else 'Нет данных'
)}

📄 **ТЕКУЩАЯ СТРАНИЦА:**
- Заголовок: {client.page_info.get('title', 'Нет') if client and client.page_info else 'Нет'}
- URL: {client.page_info.get('url', 'Нет') if client and client.page_info else 'Нет'}

📝 **ЗАДАНИЕ:**
1. Посмотри на страницу
2. Пойми, что хочет пользователь
3. Выбери правильную функцию из списка выше
4. Выполни её

⚠️ **ОТВЕЧАЙ ТОЛЬКО JSON!**

Формат ответа:
{{"action": "название_функции", "params": {{"параметр": "значение"}}}}

Примеры правильных ответов:
{{"action": "navigate", "params": {{"url": "https://google.com"}}}}
{{"action": "click", "params": {{"selector": "button:contains('Войти')"}}}}
{{"action": "fill", "params": {{"selector": "input[placeholder='Поиск']", "value": "Привет"}}}}
{{"action": "answer", "params": {{"text": "На странице Google есть поле поиска и кнопка 'Поиск в Google'"}}}}
{{"action": "screenshot", "params": {{}}}}
{{"action": "scroll", "params": {{"amount": 500}}}}
{{"action": "back", "params": {{}}}}
{{"action": "wait_for", "params": {{"selector": "button", "timeout": 10}}}}
{{"action": "get_text", "params": {{"selector": "h1"}}}}

❌ НЕПРАВИЛЬНЫЕ ОТВЕТЫ:
- Любой текст без JSON
- {"action": "click"} — нет params
- {"action": "navigate"} — нет url

🎯 **ВОТ ЧТО НА СТРАНИЦЕ ПРЯМО СЕЙЧАС:**
- Кнопки: {buttons[:5] if buttons else 'Нет данных'}
- Поля: {inputs[:5] if inputs else 'Нет данных'}
- Ссылки: {links[:5] if links else 'Нет данных'}

Используй ЭТИ данные для выбора селекторов!
"""

    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json"
    }
    
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
            await client.update_page_info()
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
                await client.update_page_info()
                return f"✅ Кликнул: {selector}"
            return f"❌ Элемент не найден: {selector}"
        
        elif action_type == "fill":
            selector = params.get("selector")
            value = params.get("value", "")
            if not selector:
                return "❌ Нет селектора"
            result = await client.fill_element(selector, value)
            if result and result.get("success"):
                await client.update_page_info()
                return f"✅ Заполнил: {selector} = {value}"
            return f"❌ Элемент не найден: {selector}"
        
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
            await client.update_page_info()
            return "✅ Назад"
        
        elif action_type == "forward":
            await client.forward()
            await client.update_page_info()
            return "✅ Вперёд"
        
        elif action_type == "reload":
            await client.reload()
            await client.update_page_info()
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
        
        # Агент с видимостью кода
        if AGNES_API_KEY:
            response = await ask_agnes_with_code(prompt, client)
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
        "🤖 **АГЕНТ С ВИДИМЫМ КОДОМ**\n\n"
        "Я вижу свой код и знаю, что могу:\n"
        "• navigate() — открывать сайты\n"
        "• click() — кликать по кнопкам\n"
        "• fill() — заполнять поля\n"
        "• screenshot() — делать скриншоты\n"
        "• answer() — отвечать на вопросы\n"
        "• scroll() — прокручивать\n"
        "• wait_for() — ждать элементы\n"
        "• get_text() — читать текст\n\n"
        "💡 **Примеры команд:**\n"
        "• Открой Google\n"
        "• Нажми на кнопку Войти\n"
        "• Введи в поле текст Привет\n"
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