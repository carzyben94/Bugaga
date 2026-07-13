import os
import json
import time
import subprocess
import base64
import requests
import asyncio
import websockets
import random
import hashlib
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ---------- КОНФИГ ----------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "ВАШ_ТОКЕН")
CHROME_PATH = os.getenv("CHROME_PATH", "/usr/bin/google-chrome")
CDP_PORT = 9222

# ---------- AGNES AI API ----------
AGNES_API_KEY = os.getenv("AGNES_API_KEY", "ваш_api_ключ")
AGNES_API_URL = "https://apihub.agnes-ai.com/v1/chat/completions"

# ---------- КУКИ ----------
COOKIES = [
    {"name": "__cuid", "value": "55d2d7c5-4888-430a-b024-dd785da46ef4"},
    {"name": "lang", "value": "ru"},
    {"name": "dnt", "value": "1"},
    {"name": "guest_id", "value": "v1%3A178267838599411411"},
    {"name": "guest_id_marketing", "value": "v1%3A178267838599411411"},
    {"name": "guest_id_ads", "value": "v1%3A178267838599411411"},
    {"name": "personalization_id", "value": '"v1_DKrxLZAC902dMFdd1QrVYg=="'},
    {"name": "twid", "value": "u%3D2067347503503052800"},
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb"},
    {"name": "__cf_bm", "value": "DKjbDyjx2QirHfmkqVMEiM2Q9FZWkmQRWl7QI8XLKjs-1783962953.1855185-1.0.1.1-CjA58gOnYa62PucjDc.DLVoFW4q7encZTCVGJqwLMENwM3pLXQ2rLX6DdDuE_SFFjQRrFSk3LLEigrhGTLwrLN8RPyfLPBPiIGZZui7lAFIYEAd90bQLkdzLfWy827.2"}
]

# ---------- ЛОГИРОВАНИЕ ----------
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

# ---------- AI АГЕНТ ----------
class AgnesAI:
    def __init__(self, api_key=AGNES_API_KEY):
        self.api_key = api_key
        self.api_url = AGNES_API_URL
    
    async def ask(self, prompt, context=None, history=None):
        try:
            messages = [
                {
                    "role": "system",
                    "content": """Ты - AI-агент для автоматизации браузера.

Ты получаешь структуру страницы и принимаешь решения.

Правила:
1. Если страница пустая - ответь {"action": "wait", "reason": "жду загрузки"}
2. Если видишь кнопку - нажми её
3. Если есть поле ввода - напиши в него
4. Отвечай ТОЛЬКО в формате JSON

Формат ответа:
{"action": "click|type|scroll|wait|get|done", "selector": "css_selector", "text": "текст", "reason": "почему"}"""
                }
            ]
            
            if history:
                for h in history[-5:]:
                    messages.append({"role": "assistant", "content": json.dumps(h)})
            
            if context:
                messages.append({
                    "role": "user",
                    "content": f"Структура страницы:\n{context}\n\nЗадача: {prompt}"
                })
            else:
                messages.append({
                    "role": "user",
                    "content": prompt
                })
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "agnes-2.0-flash",
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                file_logger.log(f"AI ответ: {content[:100]}...", "INFO")
                
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                else:
                    return {"action": "done", "reason": "Задача выполнена"}
            else:
                file_logger.log(f"Ошибка AI API: {response.status_code}", "ERROR")
                return {"action": "error", "reason": f"Ошибка API: {response.status_code}"}
                
        except Exception as e:
            file_logger.log(f"Ошибка AI: {e}", "ERROR")
            return {"action": "error", "reason": str(e)}

# ---------- МАСКИРОВКА ----------
def get_random_window_position():
    return {
        "left": random.randint(50, 300),
        "top": random.randint(50, 200),
        "width": random.randint(1200, 1920),
        "height": random.randint(800, 1080)
    }

def get_random_user_agent():
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
    ]
    return random.choice(user_agents)

def get_random_webgl_vendor():
    vendors = [
        "Google Inc. (NVIDIA)",
        "Google Inc. (AMD)",
        "Google Inc. (Intel)",
        "NVIDIA Corporation",
        "Advanced Micro Devices, Inc.",
        "Intel Corporation"
    ]
    return random.choice(vendors)

def get_random_webgl_renderer():
    renderers = [
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (AMD, AMD Radeon RX 6800 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3090 Direct3D11 vs_5_0 ps_5_0, D3D11)"
    ]
    return random.choice(renderers)

def get_launch_args():
    window = get_random_window_position()
    
    args = [
        CHROME_PATH,
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--disable-automation",
        "--use-gl=egl",
        "--ignore-gpu-blocklist",
        "--enable-gpu-rasterization",
        "--enable-zero-copy",
        "--disable-features=AudioServiceOutOfProcess,IsolateOrigins,site-per-process",
        "--disable-site-isolation-trials",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-component-extensions-with-background-pages",
        "--disable-client-side-phishing-detection",
        "--disable-crash-reporter",
        "--disable-component-update",
        "--disable-logging",
        "--disable-prompt-on-repost",
        "--disable-sync",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-breakpad",
        "--disable-ipc-flooding-protection",
        "--disable-renderer-backgrounding",
        f"--window-position={window['left']},{window['top']}",
        f"--window-size={window['width']},{window['height']}",
        "--no-default-browser-check",
        "--no-first-run",
        "--force-color-profile=srgb",
        "--metrics-recording-only",
        "--password-store=basic",
        "--use-mock-keychain",
        "--export-tagged-pdf",
        "--enable-features=NetworkService,NetworkServiceInProcess",
        f"--user-agent={get_random_user_agent()}",
        f"--remote-debugging-port={CDP_PORT}"
    ]
    
    return args

# ---------- БРАУЗЕР ----------
class BrowserCDP:
    def __init__(self):
        self.ws = None
        self.msg_id = 0
        self.session_id = None
        self.target_id = None
        self.webgl_vendor = get_random_webgl_vendor()
        self.webgl_renderer = get_random_webgl_renderer()
        self.cookies = COOKIES
        self.agent_active = False
        self.current_task = None
        self.current_url = None
        self.action_history = []
        self.snapshot = {}
        self.connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
    
    def ensure_browser(self):
        """Проверяет и запускает Chrome"""
        try:
            requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
            file_logger.log("Chrome уже запущен", "INFO")
            return True
        except:
            file_logger.log("Запускаю Chrome...", "INFO")
            try:
                args = get_launch_args()
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # Ждём, пока Chrome запустится
                for attempt in range(15):
                    try:
                        resp = requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
                        if resp.status_code == 200:
                            file_logger.log("Chrome запущен и отвечает", "INFO")
                            return True
                    except:
                        pass
                    time.sleep(1)
                
                file_logger.log("Chrome не отвечает после запуска", "ERROR")
                return False
            except Exception as e:
                file_logger.log(f"Не удалось запустить Chrome: {e}", "ERROR")
                return False
    
    async def connect_with_retry(self):
        """Подключение с повторными попытками"""
        for attempt in range(self.max_reconnect_attempts):
            try:
                if not self.ensure_browser():
                    file_logger.log("Chrome не запущен", "ERROR")
                    await asyncio.sleep(2)
                    continue
                
                return await self.connect()
                
            except Exception as e:
                file_logger.log(f"⚠️ Попытка {attempt+1}/{self.max_reconnect_attempts}: {e}")
                await asyncio.sleep(2 ** attempt)
        
        file_logger.log("❌ Не удалось подключиться после всех попыток", "ERROR")
        return False
    
    async def ensure_connection(self):
        """Гарантирует активное соединение"""
        if not self.connected or not self.ws:
            return await self.connect_with_retry()
        
        try:
            await asyncio.wait_for(
                self.send("Runtime.evaluate", {"expression": "1"}),
                timeout=5
            )
            return True
        except:
            file_logger.log("⚠️ Соединение потеряно, переподключаюсь...")
            return await self.connect_with_retry()
    
    async def connect(self):
        if self.connected:
            return True
        
        file_logger.log("Подключение к браузеру...")
        
        # Получаем WebSocket URL
        try:
            resp = requests.get(f"http://localhost:{CDP_PORT}/json/version")
            ws_url = resp.json()["webSocketDebuggerUrl"]
        except:
            # Пробуем через /json/list
            try:
                resp = requests.get(f"http://localhost:{CDP_PORT}/json/list")
                pages = resp.json()
                ws_url = None
                for page in pages:
                    if page.get("type") == "page":
                        ws_url = page.get("webSocketDebuggerUrl")
                        break
                if not ws_url:
                    file_logger.log("❌ Не найдена страница", "ERROR")
                    return False
            except Exception as e:
                file_logger.log(f"❌ Ошибка получения WS URL: {e}", "ERROR")
                return False
        
        try:
            self.ws = await websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=60,
                close_timeout=10,
                max_size=50 * 1024 * 1024
            )
            self.connected = True
            file_logger.log("✅ WebSocket подключен", "INFO")
            
            # Включаем домены
            await self.send("Page.enable")
            await self.send("Runtime.enable")
            await self.send("Network.enable")
            await self.send("DOM.enable")
            file_logger.log("✅ Домены включены", "INFO")
            
            # Применяем маскировку
            await self.apply_mask()
            
            # Устанавливаем куки
            if self.cookies:
                await self.set_cookies(self.cookies)
            
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Connect error: {e}", "ERROR")
            return False
    
    async def reconnect(self):
        """Переподключение при разрыве"""
        file_logger.log("🔄 Переподключение...")
        self.connected = False
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
        return await self.connect_with_retry()
    
    async def apply_mask(self):
        """Применение маскировки через JS"""
        try:
            file_logger.log("🕵️ Применяю маскировку...")
            
            mask_js = """
            (function() {
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                if (!window.chrome) {
                    window.chrome = { runtime: {} };
                }
                
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['ru-RU', 'ru', 'en-US', 'en']
                });
                
                return { success: true };
            })()
            """
            
            result = await self.eval_js(mask_js)
            if result and result.get('success'):
                file_logger.log("✅ Маскировка применена", "INFO")
                return True
            else:
                file_logger.log("⚠️ Маскировка применена частично", "WARNING")
                return False
                
        except Exception as e:
            file_logger.log(f"❌ Ошибка маскировки: {e}", "ERROR")
            return False
    
    async def set_cookies(self, cookies):
        """Установка кук"""
        try:
            file_logger.log(f"🍪 Установка {len(cookies)} кук...")
            
            cookies_list = []
            for cookie in cookies:
                cookies_list.append({
                    "name": cookie["name"],
                    "value": cookie["value"],
                    "domain": ".x.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": cookie.get("httpOnly", False),
                    "sameSite": "Lax"
                })
            
            await self.send("Network.setCookies", {
                "cookies": cookies_list
            })
            
            file_logger.log(f"✅ Установлено {len(cookies)} кук", "INFO")
            return True
        except Exception as e:
            file_logger.log(f"❌ Ошибка установки кук: {e}", "ERROR")
            return False
    
    async def send(self, method, params=None, retries=3):
        """Отправка CDP команды с повторными попытками"""
        if not self.connected:
            await self.connect_with_retry()
        
        self.msg_id += 1
        msg_id = self.msg_id
        
        msg = {
            "id": msg_id,
            "method": method,
            "params": params or {}
        }
        
        for attempt in range(retries):
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
                        if data["method"] == "Page.loadEventFired":
                            file_logger.log("✅ Page.loadEventFired", "INFO")
                        continue
                    
            except (websockets.exceptions.ConnectionClosed, asyncio.TimeoutError, Exception) as e:
                file_logger.log(f"⚠️ {method} ошибка, попытка {attempt+1}/{retries}: {e}")
                if attempt < retries - 1:
                    await self.reconnect()
                    await asyncio.sleep(1)
                else:
                    file_logger.log(f"❌ {method} не удалась после {retries} попыток", "ERROR")
                    return {"error": str(e)}
        
        return {"error": "Max retries exceeded"}
    
    async def eval_js(self, code):
        """Выполнение JavaScript в браузере"""
        try:
            resp = await self.send("Runtime.evaluate", {
                "expression": code,
                "returnByValue": True,
                "awaitPromise": True
            })
            
            if "result" in resp:
                result_obj = resp["result"]
                
                if "exceptionDetails" in result_obj:
                    file_logger.log(f"❌ JS ошибка: {result_obj['exceptionDetails']}", "ERROR")
                    return None
                
                if "result" in result_obj:
                    remote = result_obj["result"]
                    if remote.get("type") == "undefined":
                        return None
                    if "value" in remote:
                        return remote["value"]
                
                if "value" in result_obj:
                    return result_obj["value"]
            
            return None
        except Exception as e:
            file_logger.log(f"❌ eval_js error: {e}", "ERROR")
            return None
    
    async def navigate(self, url):
        """Навигация с ожиданием заголовка"""
        file_logger.log(f"🌐 Навигация на {url}", "INFO")
        
        result = await self.send("Page.navigate", {"url": url})
        
        if result and "error" in result:
            file_logger.log(f"❌ Ошибка навигации: {result['error']}", "ERROR")
            return False
        
        # Ждём появления заголовка (простой и надёжный способ)
        for i in range(15):
            await asyncio.sleep(1)
            title = await self.eval_js("document.title")
            if title and title != "":
                file_logger.log(f"📄 Страница загружена: {title}", "INFO")
                await self.get_snapshot()
                return True
        
        file_logger.log("⚠️ Таймаут загрузки страницы", "WARNING")
        return False
    
    async def get_snapshot(self):
        """Получает структуру страницы"""
        try:
            file_logger.log("📸 Делаю слепок страницы...", "INFO")
            
            # Получаем все элементы
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
                        
                        const attrs = {};
                        for (const attr of el.attributes) {
                            attrs[attr.name] = attr.value;
                        }
                        
                        const text = (el.textContent || '').trim().slice(0, 200);
                        
                        const isInteractive = (
                            tag === 'button' ||
                            tag === 'a' ||
                            attrs.role === 'button'
                        );
                        
                        const important = ['button', 'a', 'input', 'textarea', 'select', 'form',
                                          'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'img', 'video',
                                          'iframe', 'div', 'span', 'section', 'article', 'nav',
                                          'header', 'footer', 'main', 'aside', 'ul', 'ol', 'li'];
                        
                        if (important.includes(tag) || isInteractive || attrs['data-testid'] || attrs['aria-label']) {
                            result.push({
                                tag: tag,
                                text: text,
                                id: el.id || '',
                                class: el.className || '',
                                attrs: attrs,
                                visible: visible,
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height),
                                isInteractive: isInteractive
                            });
                        }
                    });
                    
                    return result;
                })()
            """)
            
            if elements is None:
                elements = []
            
            title = await self.eval_js("document.title") or "Нет заголовка"
            url = await self.eval_js("window.location.href") or "Нет URL"
            
            # Сортируем по видимости
            elements.sort(key=lambda x: x.get('visible', False), reverse=True)
            
            self.snapshot = {
                "title": title,
                "url": url,
                "total": len(elements),
                "elements": elements[:500]  # Ограничиваем для AI
            }
            
            file_logger.log(f"✅ Слепок: {len(elements)} элементов", "INFO")
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Ошибка слепка: {e}", "ERROR")
            self.snapshot = {"title": "Ошибка", "url": "Ошибка", "total": 0, "elements": []}
            return False
    
    async def click(self, selector, timeout=10):
        """Клик по элементу"""
        file_logger.log(f"🖱️ Клик на {selector}", "INFO")
        
        result = await self.eval_js(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                    setTimeout(function() {{
                        el.click();
                    }}, 300);
                    return {{ success: true }};
                }}
                return {{ success: false }};
            }})()
        """)
        
        if result and result.get('success'):
            await asyncio.sleep(1)
            await self.get_snapshot()
            self.action_history.append({"action": "click", "selector": selector, "success": True})
            return True
        
        file_logger.log(f"❌ Элемент {selector} не найден", "WARNING")
        return False
    
    async def type_text(self, selector, text, timeout=10):
        """Ввод текста в поле"""
        file_logger.log(f"⌨️ Ввод текста в {selector}", "INFO")
        
        result = await self.eval_js(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.value = '{text}';
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return {{ success: true }};
                }}
                return {{ success: false }};
            }})()
        """)
        
        if result and result.get('success'):
            await self.get_snapshot()
            self.action_history.append({"action": "type", "selector": selector, "text": text, "success": True})
            return True
        
        file_logger.log(f"❌ Элемент {selector} не найден", "WARNING")
        return False
    
    async def screenshot(self):
        """Скриншот страницы"""
        try:
            file_logger.log("📸 Делаю скриншот...", "INFO")
            
            result = await self.send("Page.captureScreenshot", {
                "format": "jpeg",
                "quality": 80,
                "captureBeyondViewport": True
            })
            
            if "result" in result and "data" in result["result"]:
                img_data = base64.b64decode(result["result"]["data"])
                file_logger.log(f"✅ Скриншот сделан ({len(img_data)} байт)", "INFO")
                return img_data
            
            return None
        except Exception as e:
            file_logger.log(f"❌ Screenshot error: {e}", "ERROR")
            return None
    
    async def close(self):
        """Закрытие сессии"""
        try:
            await self.send("Target.closeTarget", {"targetId": self.target_id})
        except:
            pass
        await self.ws.close()
        self.connected = False
        self.agent_active = False

# ---------- ОБРАБОТЧИКИ ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    file_logger.log(f"Пользователь {user} запустил бота", "INFO")
    
    await update.message.reply_text(
        "🤖 **AI-агент для автоматизации браузера**\n\n"
        "Просто напиши что нужно сделать:\n"
        "• `/agent https://x.com найди пост про AI`\n"
        "• `/agent https://x.com напиши пост Привет`\n"
        "• `/agent зайди на https://x.com`\n\n"
        "📁 `/log` — получить логи\n"
        "🔍 `/status` — статус агента\n"
        "⏹️ `/end` — завершить сессию"
    )

async def handle_agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик AI-агента"""
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи URL и задачу:\n"
            "/agent https://x.com найди пост про AI"
        )
        return
    
    url = None
    task_parts = []
    
    for arg in context.args:
        if arg.startswith(('http://', 'https://')):
            url = arg
        elif '.' in arg and ' ' not in arg and len(arg) > 3 and not arg.startswith('/'):
            url = 'https://' + arg
        else:
            task_parts.append(arg)
    
    if not url:
        full_text = " ".join(context.args)
        url_match = re.search(r'(https?://[^\s]+|[a-zA-Z0-9-]+\.[a-zA-Z]{2,}[^\s]*)', full_text)
        if url_match:
            url = url_match.group(1)
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            task_parts = full_text.replace(url_match.group(0), '').strip().split()
    
    if not url:
        await update.message.reply_text(
            "❌ Не найден URL.\n"
            "Примеры:\n"
            "/agent https://x.com найди пост\n"
            "/agent зайди на https://x.com"
        )
        return
    
    task = " ".join(task_parts) if task_parts else "проанализируй страницу"
    
    file_logger.log(f"Пользователь {user} (ID: {user_id}) запустил агента: {url} - {task}", "INFO")
    
    await update.message.reply_text(f"🤖 Запускаю агента на {url}...\n📝 Задача: {task}")
    
    try:
        browser = BrowserCDP()
        
        # Подключаемся
        if not await browser.connect_with_retry():
            await update.message.reply_text("❌ Не удалось подключиться к браузеру")
            return
        
        browser.agent_active = True
        browser.current_task = task
        browser.current_url = url
        browser.action_history = []
        
        # Навигация
        if not await browser.navigate(url):
            await update.message.reply_text("❌ Не удалось загрузить страницу")
            await browser.close()
            return
        
        # Получаем контекст
        context_data = json.dumps(browser.snapshot, ensure_ascii=False, indent=2)
        
        # Спрашиваем AI
        ai = AgnesAI()
        ai_response = await ai.ask(task, context_data)
        
        results = []
        max_actions = 5
        
        for step in range(max_actions):
            if ai_response.get("action") == "error":
                results.append(f"❌ Ошибка: {ai_response.get('reason')}")
                break
            
            if ai_response.get("action") == "done":
                results.append(f"✅ {ai_response.get('reason', 'Задача выполнена!')}")
                break
            
            if ai_response.get("action") == "wait":
                results.append("⏳ Ожидание 3 секунды...")
                await asyncio.sleep(3)
                await browser.get_snapshot()
                context_data = json.dumps(browser.snapshot, ensure_ascii=False, indent=2)
                ai_response = await ai.ask(
                    f"Задача: {task}\n\nСтраница после ожидания:\n{context_data}\n\nЧто дальше?",
                    context_data
                )
                continue
            
            action = ai_response.get("action")
            selector = ai_response.get("selector")
            text = ai_response.get("text", "")
            reason = ai_response.get("reason", "")
            
            file_logger.log(f"Шаг {step+1}: {action} на {selector} ({reason})", "INFO")
            
            if action == "click":
                success = await browser.click(selector)
                results.append(f"🖱️ Клик на {selector} - {'✅' if success else '❌'}")
            elif action == "type":
                success = await browser.type_text(selector, text)
                results.append(f"⌨️ Ввод '{text}' - {'✅' if success else '❌'}")
            elif action == "scroll":
                await browser.eval_js("window.scrollTo(0, document.body.scrollHeight);")
                results.append("📜 Скролл вниз - ✅")
            else:
                results.append(f"❌ Неизвестное действие: {action}")
                break
            
            await asyncio.sleep(2)
            
            # Обновляем контекст
            await browser.get_snapshot()
            context_data = json.dumps(browser.snapshot, ensure_ascii=False, indent=2)
            history_text = "\n".join([f"- {h.get('action')} на {h.get('selector', '')}" for h in browser.action_history[-3:]])
            
            ai_response = await ai.ask(
                f"Задача: {task}\n\nЯ выполнил: {action} на {selector}\nРезультат: {success}\n\nИстория:\n{history_text}\n\nОбновлённая страница:\n{context_data}\n\nЧто дальше?",
                context_data,
                browser.action_history
            )
        
        context.user_data['agent_session'] = {
            'browser': browser,
            'url': url,
            'task': task,
            'active': True,
            'user_id': user_id
        }
        
        screenshot = await browser.screenshot()
        
        caption = f"🤖 **Задача выполнена!**\n📍 {url}\n📝 {task}\n\n📋 **Действия:**\n" + "\n".join(results)
        
        if screenshot:
            await update.message.reply_photo(screenshot, caption=caption[:1024])
        else:
            await update.message.reply_text(caption)
        
        file_logger.log(f"Агент завершил задачу для {user}", "INFO")
        
        await update.message.reply_text(
            "💡 Теперь ты можешь просто писать команды, и агент продолжит работу:\n"
            "• Нажми на кнопку Обзор\n"
            "• Напиши привет\n"
            "• Сделай скриншот\n"
            "• Какие кнопки видишь?\n\n"
            "⏹️ /end — завершить сессию"
        )
        
    except Exception as e:
        error_msg = str(e)
        file_logger.log(f"Ошибка агента для {user}: {error_msg}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {error_msg}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает обычные сообщения (продолжение сессии агента)"""
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not context.user_data.get('agent_session'):
        if text.startswith(('http://', 'https://')) or '.' in text:
            context.args = text.split()
            await handle_agent(update, context)
            return
        else:
            await update.message.reply_text(
                "🤖 Нет активной сессии.\n"
                "Начни с команды:\n"
                "/agent https://x.com задача"
            )
            return
    
    session = context.user_data['agent_session']
    browser = session['browser']
    
    if not session.get('active', False):
        await update.message.reply_text("❌ Сессия не активна. Начни заново: /agent")
        return
    
    if session.get('user_id') != user_id:
        await update.message.reply_text("❌ У тебя нет активной сессии. Начни заново: /agent")
        return
    
    # Проверяем вопросы про кнопки
    if any(word in text.lower() for word in ['какие кнопки', 'кнопки видишь', 'что видишь', 'что на странице', 'есть ли']):
        await browser.get_snapshot()
        snapshot = browser.snapshot
        
        response = "🔍 **Что я вижу на странице:**\n\n"
        
        buttons = [el for el in snapshot.get('elements', []) if el.get('isInteractive') or el.get('tag') in ['button', 'a']]
        fields = [el for el in snapshot.get('elements', []) if el.get('tag') in ['input', 'textarea', 'select']]
        
        if buttons:
            response += "🖱️ **Кнопки:**\n"
            for i, btn in enumerate(buttons[:15], 1):
                text_btn = btn.get('text', '') or btn.get('attrs', {}).get('aria-label', '') or btn.get('attrs', {}).get('data-testid', '')
                response += f"  {i}. {text_btn[:30]}\n"
        
        if fields:
            response += "\n⌨️ **Поля ввода:**\n"
            for field in fields[:10]:
                placeholder = field.get('attrs', {}).get('placeholder', '') or field.get('attrs', {}).get('aria-label', '')
                if placeholder:
                    response += f"  • {placeholder[:30]}\n"
        
        if not buttons and not fields:
            response += "⚠️ На странице не найдено кнопок или полей ввода.\n"
        
        await update.message.reply_text(response[:4000])
        return
    
    file_logger.log(f"Продолжение сессии для {user}: {text}", "INFO")
    
    try:
        # Проверяем соединение
        if not await browser.ensure_connection():
            await update.message.reply_text("❌ Потеряно соединение с браузером")
            return
        
        # Обновляем snapshot
        await browser.get_snapshot()
        context_data = json.dumps(browser.snapshot, ensure_ascii=False, indent=2)
        
        ai = AgnesAI()
        prompt = f"""
        Ты уже на странице {session['url']}
        Задача: {session['task']}
        История действий: {browser.action_history[-3:]}
        
        Пользователь говорит: {text}
        
        Что мне сделать? Ответь в формате JSON.
        """
        
        ai_response = await ai.ask(prompt, context_data, browser.action_history)
        
        if ai_response.get("action") == "error":
            await update.message.reply_text(f"❌ Ошибка: {ai_response.get('reason')}")
            return
        
        if ai_response.get("action") == "done":
            await update.message.reply_text(f"✅ {ai_response.get('reason', 'Задача выполнена!')}")
            screenshot = await browser.screenshot()
            if screenshot:
                await update.message.reply_photo(screenshot, caption="📸 Финальный скриншот")
            session['active'] = False
            return
        
        if ai_response.get("action") == "wait":
            await update.message.reply_text("⏳ Ожидание 3 секунды...")
            await asyncio.sleep(3)
            await browser.get_snapshot()
            context_data = json.dumps(browser.snapshot, ensure_ascii=False, indent=2)
            ai_response = await ai.ask(
                f"Задача: {session['task']}\n\nСтраница после ожидания:\n{context_data}\n\nЧто дальше?",
                context_data
            )
            if ai_response.get("action") == "done":
                await update.message.reply_text(f"✅ {ai_response.get('reason', 'Задача выполнена!')}")
                screenshot = await browser.screenshot()
                if screenshot:
                    await update.message.reply_photo(screenshot, caption="📸 Финальный скриншот")
                session['active'] = False
            return
        
        action = ai_response.get("action")
        selector = ai_response.get("selector")
        text = ai_response.get("text", "")
        reason = ai_response.get("reason", "")
        
        file_logger.log(f"Продолжение: {action} на {selector} ({reason})", "INFO")
        
        if action == "click":
            success = await browser.click(selector)
            await update.message.reply_text(f"🖱️ Клик на {selector} - {'✅' if success else '❌'}")
        elif action == "type":
            success = await browser.type_text(selector, text)
            await update.message.reply_text(f"⌨️ Ввод '{text}' - {'✅' if success else '❌'}")
        elif action == "wait":
            await asyncio.sleep(3)
            await update.message.reply_text("⏳ Ожидание 3 сек - ✅")
        elif action == "scroll":
            await browser.eval_js("window.scrollTo(0, document.body.scrollHeight);")
            await update.message.reply_text("📜 Скролл вниз - ✅")
        else:
            await update.message.reply_text(f"❌ Неизвестное действие: {action}")
            return
        
        screenshot = await browser.screenshot()
        if screenshot:
            await update.message.reply_photo(screenshot, caption=f"📸 После действия: {action}")
        
        # Следующий шаг
        await browser.get_snapshot()
        context_data = json.dumps(browser.snapshot, ensure_ascii=False, indent=2)
        next_response = await ai.ask(
            f"Задача: {session['task']}\n\nЧто дальше?",
            context_data,
            browser.action_history
        )
        
        if next_response.get("action") == "done":
            await update.message.reply_text(f"✅ {next_response.get('reason', 'Задача выполнена!')}")
            screenshot = await browser.screenshot()
            if screenshot:
                await update.message.reply_photo(screenshot, caption="📸 Финальный скриншот")
            session['active'] = False
        else:
            await update.message.reply_text(
                f"💡 Продолжаю работу. Просто напиши что дальше.\n"
                f"📝 Текущая задача: {session['task']}\n\n"
                f"💡 Спроси: какие кнопки видишь?\n"
                f"⏹️ /end — завершить сессию"
            )
        
    except Exception as e:
        error_msg = str(e)
        file_logger.log(f"Ошибка: {error_msg}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {error_msg}\n💡 Сессия завершена. Начни заново: /agent")
        session['active'] = False

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if context.user_data.get('agent_session') and context.user_data['agent_session'].get('active', False):
        session = context.user_data['agent_session']
        if session.get('user_id') != user_id:
            await update.message.reply_text("🤖 Нет активной сессии для тебя.")
            return
        
        browser = session['browser']
        await update.message.reply_text(
            f"🤖 **Активная сессия:**\n"
            f"📍 {session['url']}\n"
            f"📝 {session['task']}\n"
            f"📊 Действий выполнено: {len(browser.action_history)}\n"
            f"📄 Элементов на странице: {browser.snapshot.get('total', 0)}\n\n"
            f"💡 Просто напиши что сделать дальше!\n"
            f"⏹️ /end — завершить сессию"
        )
    else:
        await update.message.reply_text(
            "🤖 Нет активной сессии.\n"
            "Начни с команды:\n"
            "/agent https://x.com задача"
        )

async def end_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    user_id = update.effective_user.id
    
    if not context.user_data.get('agent_session'):
        await update.message.reply_text("🤖 Нет активной сессии для завершения")
        return
    
    session = context.user_data['agent_session']
    
    if session.get('user_id') != user_id:
        await update.message.reply_text("⛔ У тебя нет активной сессии для завершения.")
        return
    
    browser = session.get('browser')
    if browser:
        try:
            await browser.close()
        except:
            pass
    
    context.user_data['agent_session'] = None
    file_logger.log(f"Пользователь {user} завершил сессию", "INFO")
    
    await update.message.reply_text(
        "✅ **Сессия завершена!**\n\n"
        "Чтобы начать новую:\n"
        "/agent https://x.com задача"
    )

async def get_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not os.path.exists(LOG_FILE):
            await update.message.reply_text("📭 Логов нет")
            return
        
        with open(LOG_FILE, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=f"bot_logs_{time.strftime('%Y-%m-%d')}.txt"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ---------- ЗАПУСК ----------
def main():
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "ВАШ_ТОКЕН":
        print("❌ Укажи TELEGRAM_BOT_TOKEN в .env файле!")
        return
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("log", get_log))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("end", end_session))
    app.add_handler(CommandHandler("agent", handle_agent))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен!")
    print("🤖 AI-агент: /agent https://x.com задача")
    print("📁 Логи: /log")
    print("🔍 Статус: /status")
    print("⏹️ /end - завершить")
    print("💡 Просто пиши команды после запуска агента!")
    
    app.run_polling()

if __name__ == "__main__":
    main()