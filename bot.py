import os
import logging
import json
import subprocess
import time
import requests
import re
import base64
import asyncio
import random
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

# ---------- КУКИ ДЛЯ X.COM ----------
X_COOKIES = [
    {"name": "__cuid", "value": "55d2d7c5-4888-430a-b024-dd785da46ef4", "domain": ".x.com", "path": "/"},
    {"name": "lang", "value": "ru", "domain": ".x.com", "path": "/"},
    {"name": "dnt", "value": "1", "domain": ".x.com", "path": "/"},
    {"name": "guest_id", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_marketing", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_ads", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "personalization_id", "value": '"v1_DKrxLZAC902dMFdd1QrVYg=="', "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"},
    {"name": "__cf_bm", "value": "j2mG_0c5w5JQUmv58SK5rLYOjV1pvjNGDsoZIMJGYv4-1783776014.9041774-1.0.1.1-adjQms4xp_hAMnqNEjMJP5_YPV7H5SdSeWNpQ_1wPS1zpCM3.mSKXJQLEbTDX6EHcG4P97tYtVLugjDWgXXQD0hSdc1V7Ogii9S6Mksik2X1pxvCyCAAFjUNXBvOPu0s", "domain": ".x.com", "path": "/"}
]

# ---------- ДИАЛОГОВАЯ ПОЛИТИКА (из Hermes) ----------
DIALOG_POLICY = {
    "must_respond": "wait",      # Ждать ответа агента
    "auto_dismiss": "dismiss",   # Автоматически закрывать
    "auto_accept": "accept"      # Автоматически принимать
}
CURRENT_DIALOG_POLICY = "must_respond"  # По умолчанию

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
            "--window-size=1920,1080",
            
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-web-security",
            "--disable-site-isolation-trials",
            "--disable-features=BlockInsecurePrivateNetworkRequests",
            "--disable-features=TranslateUI,BlinkGenPropertyTrees",
            
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            
            "--disable-default-apps",
            "--disable-extensions",
            "--disable-component-extensions-with-background-pages",
            "--disable-client-side-phishing-detection",
            "--disable-hang-monitor",
            "--disable-ipc-flooding-protection",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-sync",
            "--disable-breakpad",
            
            "--metrics-recording-only",
            "--no-first-run",
            "--safebrowsing-disable-auto-update",
            "--force-color-profile=srgb",
            
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            
            "--enable-automation"
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
        self.cookies_set = False
        self.pending_dialogs = []
        self.connected_tabs = {}
        self.dialog_timeout = 300  # 5 минут таймаут для диалогов
    
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
                ping_interval=60,
                ping_timeout=180,
                close_timeout=30,
                max_size=20_000_000
            )
            self.connected = True
            file_logger.log("✅ WebSocket подключен")
            
            await self.send("Page.enable", {})
            await self.send("Runtime.enable", {})
            await self.send("DOM.enable", {})
            await self.send("Network.enable", {})
            
            await self.send("Target.setAutoAttach", {
                "autoAttach": True,
                "flatten": True,
                "waitForDebuggerOnStart": False
            })
            file_logger.log("✅ Target.setAutoAttach включён")
            
            file_logger.log("✅ Page, Runtime, DOM, Network включены")
            
            await self.mask_browser()
            file_logger.log("✅ Браузер замаскирован")
            
            await self.set_x_cookies()
            
            await self.navigate("https://google.com")
            
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Connect error: {e}", "ERROR")
            return False
    
    async def mask_browser(self):
        try:
            js_code = """
            (function() {
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                    configurable: true
                });
                
                Object.defineProperty(navigator, 'plugins', {
                    get: () => {
                        const plugins = [
                            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                            { name: 'Native Client', filename: 'internal-nacl-plugin' }
                        ];
                        plugins.length = 3;
                        plugins.item = function(i) { return this[i]; };
                        plugins.namedItem = function(name) {
                            for (let i = 0; i < this.length; i++) {
                                if (this[i].name === name) return this[i];
                            }
                            return null;
                        };
                        return plugins;
                    },
                    configurable: true
                });
                
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['ru-RU', 'ru', 'en-US', 'en'],
                    configurable: true
                });
                
                window.chrome = {
                    runtime: {
                        connect: function() {},
                        sendMessage: function() {},
                        getManifest: function() {
                            return {
                                version: '120.0.6099.109',
                                name: 'Chrome'
                            };
                        }
                    },
                    loadTimes: function() {
                        return {
                            connectionInfo: '100mbps',
                            npnNegotiatedProtocol: 'h2',
                            wasAlternateProtocolAvailable: true,
                            wasNpnNegotiated: true
                        };
                    },
                    csi: function() {
                        return {
                            startE: Date.now() - 1000,
                            pageT: 1000
                        };
                    },
                    app: {
                        isInstalled: false,
                        getDetails: function() {},
                        installState: function() {
                            return 'disabled';
                        }
                    },
                    webstore: {
                        onInstallStageChanged: {},
                        onDownloadProgress: {}
                    }
                };
                
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) {
                        return 'Intel Inc.';
                    }
                    if (parameter === 37446) {
                        return 'Intel Iris OpenGL Engine';
                    }
                    if (parameter === 37447) {
                        return 'OpenGL 4.6';
                    }
                    return getParameter(parameter);
                };
                
                Object.defineProperty(navigator, 'connection', {
                    get: () => ({
                        effectiveType: '4g',
                        rtt: 50,
                        downlink: 10,
                        saveData: false,
                        type: 'cellular'
                    }),
                    configurable: true
                });
                
                Object.defineProperty(performance, 'memory', {
                    get: () => ({
                        totalJSHeapSize: 100000000,
                        usedJSHeapSize: 50000000,
                        jsHeapSizeLimit: 200000000
                    }),
                    configurable: true
                });
                
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 8,
                    configurable: true
                });
                
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'Win32',
                    configurable: true
                });
                
                delete window.__cdp__;
                delete window.__CDP__;
                delete window.__playwright__;
                delete window.__pw_manual__;
                delete window.__playwright_evaluation_script__;
                delete window.__pw_hook__;
                delete window.__selenium_evaluate__;
                delete window.__webdriver_evaluate__;
                delete window.__driver_unwrapped__;
                delete window.__webdriver_script_evaluate__;
                delete window.__webdriver_script_function__;
                
                if (navigator.mediaDevices) {
                    Object.defineProperty(navigator.mediaDevices, 'enumerateDevices', {
                        value: async function() {
                            return [
                                { deviceId: 'default', kind: 'audioinput', label: 'Default' },
                                { deviceId: 'default', kind: 'videoinput', label: 'Default' }
                            ];
                        }
                    });
                }
                
                Object.defineProperty(Intl.DateTimeFormat.prototype, 'resolvedOptions', {
                    value: function() {
                        const result = Object.getOwnPropertyDescriptor(
                            Intl.DateTimeFormat.prototype.resolvedOptions,
                            'value'
                        ).call(this);
                        result.timeZone = 'Europe/Moscow';
                        return result;
                    }
                });
                
                Object.defineProperty(screen, 'availWidth', { value: 1920 });
                Object.defineProperty(screen, 'availHeight', { value: 1040 });
                
                Object.defineProperty(navigator, 'doNotTrack', {
                    get: () => '1',
                    configurable: true
                });
                
                return { success: true };
            })()
            """
            return await self.eval_js(js_code)
        except Exception as e:
            file_logger.log(f"❌ Mask error: {e}", "ERROR")
            return False
    
    async def set_x_cookies(self):
        try:
            file_logger.log("🍪 Устанавливаю куки для X.com...")
            
            for cookie in X_COOKIES:
                cdp_cookie = {
                    "name": cookie["name"],
                    "value": cookie["value"],
                    "domain": cookie["domain"],
                    "path": cookie.get("path", "/"),
                    "secure": cookie.get("secure", False),
                    "httpOnly": cookie.get("httpOnly", False),
                }
                
                same_site = cookie.get("sameSite", "unspecified")
                if same_site.lower() == "none":
                    cdp_cookie["sameSite"] = "None"
                elif same_site.lower() == "lax":
                    cdp_cookie["sameSite"] = "Lax"
                elif same_site.lower() == "strict":
                    cdp_cookie["sameSite"] = "Strict"
                else:
                    cdp_cookie["sameSite"] = "Unspecified"
                
                await self.send("Network.setCookie", cdp_cookie)
                file_logger.log(f"✅ Кука установлена: {cookie['name']}")
            
            self.cookies_set = True
            file_logger.log(f"✅ Установлено {len(X_COOKIES)} кук для X.com")
            return True
        except Exception as e:
            file_logger.log(f"❌ Ошибка установки кук: {e}", "ERROR")
            return False
    
    async def safe_send(self, method, params=None, retry=3):
        last_error = None
        for attempt in range(retry):
            try:
                return await self.send(method, params)
            except Exception as e:
                last_error = e
                error_str = str(e)
                if "keepalive ping timeout" in error_str or "1011" in error_str:
                    file_logger.log(f"⚠️ Потеря соединения, переподключаюсь... (попытка {attempt+1}/{retry})")
                    self.connected = False
                    await self.connect()
                    await asyncio.sleep(2)
                else:
                    raise
        return {"error": f"Max retries exceeded: {last_error}"}
    
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
                
                # ============================================
                # 🆕 HERMES: Обработка диалогов с политикой
                # ============================================
                if "method" in data and data["method"] == "Page.javascriptDialogOpening":
                    dialog_params = data.get("params", {})
                    dialog_message = dialog_params.get('message', '')
                    dialog_type = dialog_params.get('type', '')
                    
                    file_logger.log(f"💬 Диалог обнаружен: {dialog_message} (тип: {dialog_type})")
                    
                    # Применяем политику
                    if CURRENT_DIALOG_POLICY == "auto_dismiss":
                        file_logger.log("🚫 Политика: auto_dismiss — закрываю диалог")
                        await self.send("Page.handleJavaScriptDialog", {"accept": False})
                        continue
                    elif CURRENT_DIALOG_POLICY == "auto_accept":
                        file_logger.log("✅ Политика: auto_accept — принимаю диалог")
                        await self.send("Page.handleJavaScriptDialog", {"accept": True})
                        continue
                    else:  # must_respond
                        self.pending_dialogs.append({
                            "message": dialog_message,
                            "type": dialog_type,
                            "defaultPrompt": dialog_params.get("defaultPrompt", ""),
                            "timestamp": time.time()
                        })
                        # Добавляем таймаут для диалога
                        if len(self.pending_dialogs) > 0:
                            asyncio.create_task(self._dialog_timeout_check())
                    continue
                
                if "method" in data and data["method"] == "Target.attachedToTarget":
                    target_info = data.get("params", {}).get("targetInfo", {})
                    session_id = data.get("params", {}).get("sessionId")
                    if session_id:
                        self.connected_tabs[session_id] = {
                            "target_id": target_info.get("targetId"),
                            "url": target_info.get("url"),
                            "type": target_info.get("type")
                        }
                        file_logger.log(f"🔗 Прикреплён фрейм: {target_info.get('url', '')[:50]}")
                    continue
                
                if data.get("id") == msg_id:
                    if "error" in data:
                        file_logger.log(f"❌ {method}: {data['error']}", "ERROR")
                    return data
                
        except asyncio.TimeoutError:
            file_logger.log(f"❌ {method} timeout", "ERROR")
            return {"error": "Timeout"}
        except Exception as e:
            file_logger.log(f"❌ {method} error: {e}", "ERROR")
            return {"error": str(e)}
    
    async def _dialog_timeout_check(self):
        """Проверка таймаута диалогов (Hermes)"""
        await asyncio.sleep(self.dialog_timeout)
        if self.pending_dialogs:
            file_logger.log(f"⏰ Таймаут диалога ({self.dialog_timeout}с), закрываю")
            dialog = self.pending_dialogs.pop(0)
            await self.send("Page.handleJavaScriptDialog", {"accept": False})
    
    async def navigate(self, url):
        file_logger.log(f"🌐 Навигация на {url}")
        await self.send("Page.navigate", {"url": url})
        
        if "x.com" in url.lower():
            file_logger.log("🍪 Проверяю куки для X.com...")
            if not self.cookies_set:
                await self.set_x_cookies()
            await asyncio.sleep(1)
            await self.send("Page.reload", {})
        
        for i in range(10):
            await asyncio.sleep(1)
            title = await self.eval_js("document.title")
            if title and title != "":
                file_logger.log(f"📄 Страница загружена: {title}")
                await self.get_maximum_snapshot()
                break
    
    async def eval_js(self, code):
        try:
            resp = await self.safe_send("Runtime.evaluate", {
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
                    if "objectId" in remote:
                        return remote
                
                if "value" in result_obj:
                    return result_obj["value"]
            
            return None
        except Exception as e:
            file_logger.log(f"❌ eval_js error: {e}", "ERROR")
            return None
    
    async def get_maximum_snapshot(self):
        try:
            file_logger.log("📸 Делаю максимальный слепок...")
            
            url = await self.eval_js("window.location.href") or ""
            is_x = "x.com" in url
            max_elements = 2000 if is_x else 500
            
            frame_tree_resp = await self.send("Page.getFrameTree", {})
            frame_tree = None
            if "result" in frame_tree_resp:
                frame_tree = frame_tree_resp["result"].get("frameTree", {})
                file_logger.log(f"📦 FrameTree получен")
            
            result = await self.eval_js(f"""
                (function() {{
                    const result = [];
                    const all = document.querySelectorAll('*');
                    let count = 0;
                    const maxCount = {max_elements};
                    
                    for (const el of all) {{
                        if (count >= maxCount) break;
                        
                        const tag = el.tagName.toLowerCase();
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        
                        const visible = rect.width > 0 && rect.height > 0 && 
                                       style.display !== 'none' && 
                                       style.visibility !== 'hidden';
                        
                        const attrs = {{}};
                        for (const attr of el.attributes) {{
                            attrs[attr.name] = attr.value;
                        }}
                        
                        const important = ['a', 'button', 'input', 'textarea', 'select', 'form',
                                          'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'img', 'video',
                                          'iframe', 'div', 'span', 'section', 'article', 'nav',
                                          'header', 'footer', 'main', 'aside', 'ul', 'ol', 'li',
                                          'label', 'option', 'legend', 'fieldset', 'dialog'];
                        
                        if (important.includes(tag)) {{
                            result.push({{
                                tag: tag,
                                text: (el.textContent || '').trim().slice(0, 100),
                                id: el.id || '',
                                class: el.className || '',
                                attrs: attrs,
                                visible: visible,
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height),
                                style: {{
                                    display: style.display,
                                    visibility: style.visibility,
                                    position: style.position,
                                    color: style.color,
                                    fontSize: style.fontSize,
                                    backgroundColor: style.backgroundColor,
                                    cursor: style.cursor
                                }},
                                parent: el.parentElement ? el.parentElement.tagName.toLowerCase() : null,
                                children: el.children.length
                            }});
                            count++;
                        }}
                    }}
                    
                    return result;
                }})()
            """)
            
            if result is None:
                elements = []
            elif isinstance(result, list):
                elements = result
            elif isinstance(result, str):
                try:
                    parsed = json.loads(result)
                    if isinstance(parsed, list):
                        elements = parsed
                    else:
                        elements = []
                except:
                    elements = []
            else:
                elements = []
            
            if not elements:
                simple_result = await self.eval_js("""
                    (function() {
                        const result = [];
                        document.querySelectorAll('button, a, input, textarea, select, form, h1, h2, h3').forEach(el => {
                            result.push({
                                tag: el.tagName.toLowerCase(),
                                text: (el.textContent || el.value || '').trim().slice(0, 50),
                                id: el.id || '',
                                class: el.className || ''
                            });
                        });
                        return result;
                    })()
                """)
                if isinstance(simple_result, list):
                    elements = simple_result
                    file_logger.log(f"✅ Упрощённый сбор: {len(elements)} элементов")
            
            if len(elements) > max_elements:
                elements = elements[:max_elements]
                file_logger.log(f"⚠️ Ограничил слепок до {max_elements} элементов")
            
            title = await self.eval_js("document.title") or "Нет заголовка"
            url_final = await self.eval_js("window.location.href") or "Нет URL"
            
            if self.pending_dialogs:
                file_logger.log(f"💬 Есть ожидающие диалоги: {len(self.pending_dialogs)}")
            
            all_fields = []
            
            inputs = [e for e in elements if e.get('tag') == 'input']
            for inp in inputs:
                attrs = inp.get('attrs', {})
                inp['field_type'] = 'input'
                inp['field_selector'] = f"input[name='{attrs.get('name', '')}']" if attrs.get('name') else f"input[type='{attrs.get('type', 'text')}']"
                all_fields.append(inp)
            
            textareas = [e for e in elements if e.get('tag') == 'textarea']
            for ta in textareas:
                attrs = ta.get('attrs', {})
                ta['field_type'] = 'textarea'
                ta['field_selector'] = f"textarea[name='{attrs.get('name', '')}']" if attrs.get('name') else "textarea"
                all_fields.append(ta)
            
            selects = [e for e in elements if e.get('tag') == 'select']
            for sel in selects:
                attrs = sel.get('attrs', {})
                sel['field_type'] = 'select'
                sel['field_selector'] = f"select[name='{attrs.get('name', '')}']" if attrs.get('name') else "select"
                all_fields.append(sel)
            
            contenteditables = [e for e in elements if e.get('attrs', {}).get('contenteditable') == 'true']
            for ce in contenteditables:
                class_name = ce.get('class', '')
                if isinstance(class_name, list):
                    class_name = ' '.join(class_name)
                
                if ce.get('id'):
                    ce['field_selector'] = f"#{ce.get('id')}"
                elif class_name:
                    ce['field_selector'] = f".{class_name.replace(' ', '.')}"
                else:
                    ce['field_selector'] = "div[contenteditable='true']"
                all_fields.append(ce)
            
            roles = [e for e in elements if e.get('attrs', {}).get('role') in ['textbox', 'searchbox', 'combobox']]
            for role in roles:
                role['field_type'] = 'role'
                role['field_selector'] = role.get('id') and f"#{role.get('id')}" or f"[role='{role.get('attrs', {}).get('role')}']"
                all_fields.append(role)
            
            # ============================================
            # ✅ УЛУЧШЕННЫЙ СБОР КНОПОК
            # ============================================
            buttons = []
            button_texts = set()
            
            for el in elements:
                tag = el.get('tag', '')
                attrs = el.get('attrs', {})
                role = attrs.get('role', '')
                class_name = attrs.get('class', '')
                if isinstance(class_name, list):
                    class_name = ' '.join(class_name)
                class_name_lower = class_name.lower() if isinstance(class_name, str) else ''
                text = el.get('text', '') or attrs.get('value', '') or attrs.get('aria-label', '') or attrs.get('title', '')
                
                is_button = False
                
                if tag == 'button':
                    is_button = True
                elif tag == 'input' and attrs.get('type') in ['submit', 'button', 'image']:
                    is_button = True
                elif role == 'button':
                    is_button = True
                elif tag == 'a' and (role == 'button' or 'button' in class_name_lower):
                    is_button = True
                elif tag in ['div', 'span'] and role == 'button':
                    is_button = True
                elif 'btn' in class_name_lower or 'button' in class_name_lower:
                    is_button = True
                elif attrs.get('onclick') or attrs.get('data-action') or attrs.get('data-testid', '').endswith('btn'):
                    is_button = True
                elif attrs.get('tabindex') and attrs.get('role') in ['link', 'menuitem', 'option']:
                    is_button = True
                elif 'button' in attrs.get('aria-label', '').lower() or 'btn' in attrs.get('aria-label', '').lower():
                    is_button = True
                
                if is_button:
                    if text:
                        if text not in button_texts:
                            button_texts.add(text)
                            buttons.append(el)
                    else:
                        unique_key = f"{tag}_{attrs.get('data-testid', '')}"
                        if unique_key not in button_texts:
                            button_texts.add(unique_key)
                            buttons.append(el)
            
            for el in elements:
                attrs = el.get('attrs', {})
                role = attrs.get('role', '')
                if role == 'button' and el not in buttons:
                    buttons.append(el)
            
            links = [e for e in elements if e.get('tag') == 'a' and e.get('attrs', {}).get('href')]
            forms = [e for e in elements if e.get('tag') == 'form']
            headings = [e for e in elements if e.get('tag') in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']]
            visible = [e for e in elements if e.get('visible')]
            
            self.full_snapshot = {
                "title": title,
                "url": url_final,
                "total": len(elements),
                "all_elements": elements,
                "buttons": buttons,
                "fields": all_fields,
                "inputs": inputs,
                "textareas": textareas,
                "selects": selects,
                "contenteditables": contenteditables,
                "roles": roles,
                "links": links,
                "forms": forms,
                "headings": headings,
                "visible": visible,
                "pending_dialogs": self.pending_dialogs.copy() if self.pending_dialogs else [],
                "frame_tree": frame_tree if frame_tree else None,
                "connected_tabs": self.connected_tabs.copy() if self.connected_tabs else {}
            }
            
            file_logger.log(f"✅ Максимальный слепок: {len(elements)} элементов, {len(buttons)} кнопок, {len(all_fields)} полей")
            return True
            
        except Exception as e:
            file_logger.log(f"❌ Maximum snapshot error: {e}", "ERROR")
            import traceback
            file_logger.log(traceback.format_exc(), "ERROR")
            self.full_snapshot = {
                "title": "Ошибка загрузки",
                "url": "",
                "total": 0,
                "all_elements": [],
                "buttons": [],
                "fields": [],
                "inputs": [],
                "textareas": [],
                "selects": [],
                "contenteditables": [],
                "roles": [],
                "links": [],
                "forms": [],
                "headings": [],
                "visible": [],
                "pending_dialogs": self.pending_dialogs.copy() if self.pending_dialogs else [],
                "frame_tree": None,
                "connected_tabs": self.connected_tabs.copy() if self.connected_tabs else {}
            }
            return False
    
    async def handle_dialog(self, accept=True, prompt_text=""):
        try:
            if not self.pending_dialogs:
                return {"error": "Нет ожидающих диалогов"}
            
            dialog = self.pending_dialogs.pop(0)
            result = await self.send("Page.handleJavaScriptDialog", {
                "accept": accept,
                "promptText": prompt_text
            })
            file_logger.log(f"✅ Диалог обработан: {dialog.get('message', '')}")
            return {"success": True, "dialog": dialog}
        except Exception as e:
            file_logger.log(f"❌ Dialog error: {e}", "ERROR")
            return {"error": str(e)}
    
    async def cdp_command(self, method, params=None, frame_id=None):
        try:
            if frame_id:
                session_id = None
                for sid, info in self.connected_tabs.items():
                    if info.get("target_id") == frame_id:
                        session_id = sid
                        break
                if session_id:
                    return await self.send(method, params, session_id)
            
            return await self.send(method, params)
        except Exception as e:
            file_logger.log(f"❌ CDP command error: {e}", "ERROR")
            return {"error": str(e)}
    
    async def set_dialog_policy(self, policy):
        """Устанавливает политику для диалогов (Hermes)"""
        global CURRENT_DIALOG_POLICY
        if policy in DIALOG_POLICY:
            CURRENT_DIALOG_POLICY = policy
            file_logger.log(f"📋 Политика диалогов: {policy}")
            return True
        return False
    
    async def get_page_description(self):
        if not self.full_snapshot:
            await self.get_maximum_snapshot()
        
        info = self.full_snapshot or {}
        
        title = info.get('title', 'Нет заголовка') if isinstance(info, dict) else 'Нет заголовка'
        url = info.get('url', 'Нет URL') if isinstance(info, dict) else 'Нет URL'
        total = info.get('total', 0) if isinstance(info, dict) else 0
        
        desc = f"""
📄 СТРАНИЦА: {title}
🔗 URL: {url}
📊 ВСЕГО ЭЛЕМЕНТОВ: {total}

🔘 КНОПКИ ({len(info.get('buttons', [])) if isinstance(info.get('buttons', []), list) else 0}):
"""
        
        buttons = info.get('buttons') if isinstance(info, dict) else None
        if buttons is None:
            desc += "  • (нет данных)\n"
        elif isinstance(buttons, list):
            if len(buttons) == 0:
                desc += "  • (нет кнопок)\n"
            else:
                for el in buttons[:30]:
                    if isinstance(el, dict):
                        text = el.get('text', '')
                        if not text:
                            text = el.get('attrs', {}).get('value', '')
                        if not text:
                            text = el.get('attrs', {}).get('aria-label', '')
                        if not text:
                            text = el.get('attrs', {}).get('title', '')
                        if text:
                            desc += f"  • {text[:40]}\n"
                        else:
                            desc += f"  • <{el.get('tag', 'unknown')}>\n"
                    elif isinstance(el, str):
                        desc += f"  • {el[:40]}\n"
        else:
            desc += f"  • (неизвестный формат: {type(buttons).__name__})\n"
        
        desc += f"\n📝 ПОЛЯ ВВОДА:\n"
        
        fields = info.get('fields') if isinstance(info, dict) else None
        if fields is None:
            desc += "  • (нет данных)\n"
        elif isinstance(fields, list):
            if len(fields) == 0:
                desc += "  • (нет полей)\n"
            else:
                for el in fields[:20]:
                    if isinstance(el, dict):
                        attrs = el.get('attrs', {})
                        field_type = el.get('field_type', 'unknown')
                        name = attrs.get('name', '')
                        placeholder = attrs.get('placeholder', '')
                        field_name = name or placeholder or f"{field_type}"
                        selector = el.get('field_selector', '')
                        desc += f"  • {field_name[:30]} → {selector}\n"
                    elif isinstance(el, str):
                        desc += f"  • {el[:30]}\n"
        else:
            desc += f"  • (неизвестный формат: {type(fields).__name__})\n"
        
        desc += f"\n🔗 ССЫЛКИ:\n"
        
        links = info.get('links') if isinstance(info, dict) else None
        if links is None:
            desc += "  • (нет данных)\n"
        elif isinstance(links, list):
            if len(links) == 0:
                desc += "  • (нет ссылок)\n"
            else:
                for el in links[:15]:
                    if isinstance(el, dict):
                        text = el.get('text', '')[:30]
                        href = el.get('attrs', {}).get('href', '')[:50]
                        if text:
                            desc += f"  • {text} → {href}\n"
                    elif isinstance(el, str):
                        desc += f"  • {el[:30]}\n"
        else:
            desc += f"  • (неизвестный формат: {type(links).__name__})\n"
        
        # ============================================
        # 🆕 HERMES: Информация о диалогах
        # ============================================
        dialogs = info.get('pending_dialogs') if isinstance(info, dict) else None
        if dialogs and isinstance(dialogs, list) and len(dialogs) > 0:
            desc += f"\n💬 ОЖИДАЮЩИЕ ДИАЛОГИ ({len(dialogs)}):\n"
            for d in dialogs:
                desc += f"  • {d.get('message', '')} (тип: {d.get('type', 'unknown')})\n"
            desc += "\n💡 Для обработки диалога используй: handle_dialog(accept=True, prompt_text='')\n"
            desc += f"📋 Текущая политика: {CURRENT_DIALOG_POLICY}\n"
        
        # ============================================
        # 🆕 HERMES: Информация о iframe
        # ============================================
        frame_tree = info.get('frame_tree') if isinstance(info, dict) else None
        if frame_tree:
            desc += f"\n📦 IFRAME/ФРЕЙМЫ:\n"
            main_frame = frame_tree.get('frame', {})
            if main_frame:
                desc += f"  • Главный фрейм: {main_frame.get('url', '')[:60]}\n"
            
            children = frame_tree.get('childFrames', [])
            if children:
                for child in children[:5]:
                    child_url = child.get('frame', {}).get('url', '')
                    if child_url:
                        desc += f"  • Дочерний фрейм: {child_url[:60]}\n"
        
        return desc
    
    async def click_element(self, selector):
        js_code = f"""
        (function() {{
            const el = document.querySelector("{selector}");
            if (el) {{
                el.click();
                return {{ success: true }};
            }}
            return {{ success: false }};
        }})()
        """
        return await self.eval_js(js_code)
    
    async def fill_element(self, selector, value):
        escaped_value = value.replace("'", "\\'").replace('"', '\\"')
        
        js_code = f"""
        (function() {{
            const el = document.querySelector("{selector}");
            if (el) {{
                el.value = '{escaped_value}';
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
    
    async def reload(self):
        await self.send("Page.reload", {})
        await asyncio.sleep(2)
        await self.get_maximum_snapshot()
    
    async def screenshot(self):
        try:
            if not self.connected:
                await self.connect()
            
            await asyncio.sleep(3)
            
            title = await self.eval_js("document.title")
            file_logger.log(f"📄 Текущий заголовок: {title}")
            
            if not title or title == "":
                file_logger.log("🌐 Открываю Google...")
                await self.navigate("https://google.com")
                await asyncio.sleep(3)
            
            body = await self.eval_js("document.body.innerText.slice(0, 50)")
            if not body or body == "":
                file_logger.log("⚠️ Страница пустая, жду...")
                await asyncio.sleep(5)
            
            url = await self.eval_js("window.location.href") or ""
            
            file_logger.log("📸 Делаю скриншот...")
            
            if "x.com" in url:
                file_logger.log("📸 X.com: пробую специальный режим...")
                resp = await self.send("Page.captureScreenshot", {
                    "format": "png",
                    "fromSurface": True
                })
            else:
                resp = await self.send("Page.captureScreenshot", {
                    "format": "png",
                    "captureBeyondViewport": True,
                    "fromSurface": True
                })
            
            if "result" in resp and "data" in resp["result"]:
                img_data = base64.b64decode(resp["result"]["data"])
                if len(img_data) > 100:
                    file_logger.log("✅ Скриншот сделан")
                    return img_data
            
            return None
                
        except Exception as e:
            file_logger.log(f"❌ Screenshot error: {e}", "ERROR")
            return None

# ---------- Хранилище ----------

clients = {}

# ---------- КОД АГЕНТА ----------

AGENT_CODE = """
Ты агент для управления браузером.

ДОСТУПНЫЕ ДЕЙСТВИЯ (возвращай ТОЛЬКО JSON):
- navigate(url) - открыть сайт
- click(selector) - кликнуть по элементу
- fill(selector, value) - заполнить поле
- press_enter() - нажать Enter
- screenshot() - сделать скриншот
- answer(text) - ответить пользователю
- handle_dialog(accept, prompt_text) - обработать диалог
- cdp(method, params, frame_id) - выполнить любую CDP-команду
- set_dialog_policy(policy) - установить политику диалогов (must_respond, auto_dismiss, auto_accept)

⚠️ ВАЖНО: ВСЕГДА используй формат с "params":
{"action": "navigate", "params": {"url": "https://x.com"}}
{"action": "click", "params": {"selector": "button"}}
{"action": "answer", "params": {"text": "текст"}}

НЕ ИСПОЛЬЗУЙ формат без "params":
{"action": "navigate", "url": "..."}  ← НЕПРАВИЛЬНО!

ОТВЕЧАЙ ТОЛЬКО JSON! БЕЗ ЛИШНИХ СЛОВ!
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

📄 СТРАНИЦА:
{page_desc}

📝 ОТВЕЧАЙ ТОЛЬКО JSON!
"""

    data = {
        "model": "agnes-2.0-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 300
    }
    
    for attempt in range(3):
        try:
            response = requests.post(AGNES_API_URL, headers=headers, json=data, timeout=60)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            
            file_logger.log(f"Agnes ответ: {content[:200]}...")
            
            json_match = re.search(r'\[.*\]|\{.*\}', content, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                    
                    if isinstance(result, dict):
                        if 'url' in result and 'params' not in result:
                            file_logger.log("⚠️ Исправляю формат: добавил params")
                            action = result.get('action', 'navigate')
                            url = result.get('url')
                            result = {"action": action, "params": {"url": url}}
                        if 'text' in result and 'params' not in result:
                            file_logger.log("⚠️ Исправляю формат: добавил params")
                            result = {"action": "answer", "params": {"text": result.get('text')}}
                        if 'selector' in result and 'params' not in result:
                            file_logger.log("⚠️ Исправляю формат: добавил params")
                            result = {"action": "click", "params": {"selector": result.get('selector')}}
                        if 'value' in result and 'params' not in result:
                            file_logger.log("⚠️ Исправляю формат: добавил params")
                            result = {"action": "fill", "params": {"selector": result.get('selector', 'input'), "value": result.get('value')}}
                        if 'policy' in result and 'params' not in result:
                            file_logger.log("⚠️ Исправляю формат: добавил params")
                            result = {"action": "set_dialog_policy", "params": {"policy": result.get('policy')}}
                    
                    if isinstance(result, list):
                        for i, item in enumerate(result):
                            if isinstance(item, dict):
                                if 'url' in item and 'params' not in item:
                                    result[i] = {"action": item.get('action', 'navigate'), "params": {"url": item.get('url')}}
                                if 'text' in item and 'params' not in item:
                                    result[i] = {"action": "answer", "params": {"text": item.get('text')}}
                                if 'selector' in item and 'params' not in item:
                                    result[i] = {"action": "click", "params": {"selector": item.get('selector')}}
                                if 'value' in item and 'params' not in item:
                                    result[i] = {"action": "fill", "params": {"selector": item.get('selector', 'input'), "value": item.get('value')}}
                                if 'policy' in item and 'params' not in item:
                                    result[i] = {"action": "set_dialog_policy", "params": {"policy": item.get('policy')}}
                    
                    if isinstance(result, list) or (isinstance(result, dict) and 'action' in result):
                        return result
                except Exception as e:
                    file_logger.log(f"⚠️ Ошибка парсинга JSON: {e}")
                    pass
            
            return {"action": "answer", "params": {"text": content}}
        except requests.exceptions.Timeout:
            file_logger.log(f"⚠️ Попытка {attempt + 1} таймаут, повтор...")
            if attempt == 2:
                return {"action": "answer", "params": {"text": "⏳ Превышено время ожидания. Попробуйте ещё раз."}}
            await asyncio.sleep(2)
        except Exception as e:
            file_logger.log(f"Agnes error: {e}", "ERROR")
            return {"action": "answer", "params": {"text": f"❌ Ошибка: {str(e)}"}}
    
    return {"action": "answer", "params": {"text": "❌ Не удалось получить ответ"}}

# ---------- Выполнение действий ----------

async def execute_action(client: CDPClient, action) -> str:
    if isinstance(action, list):
        results = []
        for a in action:
            result = await execute_single_action(client, a)
            results.append(result)
        return "\n\n".join(results)
    return await execute_single_action(client, action)

async def execute_single_action(client: CDPClient, action: dict) -> str:
    action_type = action.get("action")
    params = action.get("params", {})
    
    file_logger.log(f"Выполнение: {action_type}")
    
    try:
        if action_type == "navigate":
            url = params.get("url", "https://google.com")
            await client.navigate(url)
            title = await client.eval_js("document.title")
            return f"""✅ Открыл: {url}

📄 Заголовок: {title}
🔗 URL: {url}

💡 Теперь ты можешь искать информацию или вводить текст в поля."""
        
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
        
        elif action_type == "handle_dialog":
            accept = params.get("accept", True)
            prompt_text = params.get("prompt_text", "")
            result = await client.handle_dialog(accept, prompt_text)
            if result.get("success"):
                return f"✅ Диалог обработан: {result.get('dialog', {}).get('message', '')}"
            return f"❌ Ошибка обработки диалога: {result.get('error', '')}"
        
        elif action_type == "set_dialog_policy":
            policy = params.get("policy", "must_respond")
            result = await client.set_dialog_policy(policy)
            if result:
                return f"📋 Политика диалогов изменена на: {policy}"
            return f"❌ Неверная политика: {policy}. Доступные: must_respond, auto_dismiss, auto_accept"
        
        elif action_type == "cdp":
            method = params.get("method")
            cdp_params = params.get("params", {})
            frame_id = params.get("frame_id")
            
            if not method:
                return "❌ Нет метода"
            
            result = await client.cdp_command(method, cdp_params, frame_id)
            return f"✅ CDP команда выполнена: {method}\n{json.dumps(result, indent=2, ensure_ascii=False)[:500]}"
        
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
        "/cdp - статус браузера\n"
        "/logs - логи\n"
        "/dialog_policy - политика диалогов"
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

async def dialog_policy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает текущую политику диалогов"""
    user_id = update.message.from_user.id
    if user_id not in clients:
        await update.message.reply_text("❌ Сначала откройте браузер")
        return
    
    client = clients[user_id]
    policy = getattr(client, 'dialog_policy', 'must_respond')
    await update.message.reply_text(
        f"📋 Текущая политика диалогов: **{policy}**\n\n"
        "Доступные политики:\n"
        "• must_respond - ждать ответа агента\n"
        "• auto_dismiss - автоматически закрывать\n"
        "• auto_accept - автоматически принимать"
    )

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
    app.add_handler(CommandHandler("dialog_policy", dialog_policy_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен!")
    file_logger.log("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()