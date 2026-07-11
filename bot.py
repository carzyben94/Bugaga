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
import math
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

# ---------- ДИАЛОГОВАЯ ПОЛИТИКА ----------
DIALOG_POLICY = {
    "must_respond": "wait",
    "auto_dismiss": "dismiss",
    "auto_accept": "accept"
}
CURRENT_DIALOG_POLICY = "must_respond"

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

# ============================================
# 🧠 ПОЛНЫЙ CDP SUPERVISOR (Hermes)
# ============================================

class CDPSupervisor:
    """Полноценный CDP Supervisor как в Hermes"""
    
    def __init__(self, user_id: int, ws_url: str):
        self.user_id = user_id
        self.ws_url = ws_url
        self.ws = None
        self.connected = False
        self.msg_id = 0
        self.running = False
        self.page_loaded = False
        
        # Состояние
        self.pending_dialogs = []
        self.frame_tree = {}
        self.connected_tabs = {}
        self.ref_elements = {}
        self.full_snapshot = None
        self.oopifs = {}
        
        # ✅ СИНХРОНИЗАЦИЯ (как в Hermes)
        self._pending_requests = {}  # {msg_id: asyncio.Future}
        self._recv_lock = asyncio.Lock()  # синхронизация recv
        self._stop_event = asyncio.Event()
        self._ready_event = asyncio.Event()
        
        # Таймауты
        self.dialog_timeout = 300
        self.ping_interval = 60
        self.ping_timeout = 180
        self.connection_timeout = 30
        
        # Задачи
        self.supervisor_task = None
        self.heartbeat_task = None
        self.dialog_timeout_task = None
    
    # ============================================
    # ЗАПУСК И УПРАВЛЕНИЕ
    # ============================================
    
    async def start(self):
        """Запускает супервайзера в фоне"""
        if self.running:
            return True
        
        file_logger.log(f"🧠 Запуск CDP Supervisor для {self.user_id}")
        self.running = True
        self._stop_event.clear()
        self.supervisor_task = asyncio.create_task(self._run())
        self.heartbeat_task = asyncio.create_task(self._heartbeat())
        
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=30)
            return True
        except asyncio.TimeoutError:
            file_logger.log(f"⚠️ Supervisor не готов за 30 секунд")
            return False
    
    async def stop(self):
        """Останавливает супервайзера"""
        self.running = False
        self._stop_event.set()
        
        if self.supervisor_task:
            self.supervisor_task.cancel()
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.ws:
            await self.ws.close()
        
        file_logger.log(f"🧠 CDP Supervisor остановлен для {self.user_id}")
    
    # ============================================
    # ОСНОВНОЙ ЦИКЛ
    # ============================================
    
    async def _run(self):
        """Основной цикл супервайзера"""
        while self.running and not self._stop_event.is_set():
            try:
                await self._connect()
                await self._setup_domains()
                await self._navigate_to_default()
                self._ready_event.set()
                await self._event_loop()  # ✅ ВЫЗЫВАЕМ _event_loop
            except websockets.ConnectionClosed:
                file_logger.log(f"⚠️ WebSocket закрыт, переподключаюсь...")
                await asyncio.sleep(5)
            except Exception as e:
                file_logger.log(f"❌ Supervisor error: {e}", "ERROR")
                await asyncio.sleep(5)
    
    # ============================================
    # ПОДКЛЮЧЕНИЕ
    # ============================================
    
    async def _connect(self):
        """Подключается к Chrome"""
        file_logger.log(f"🔗 Подключение к Chrome для {self.user_id}")
        self.ws = await websockets.connect(
            self.ws_url,
            ping_interval=self.ping_interval,
            ping_timeout=self.ping_timeout,
            close_timeout=30,
            max_size=20_000_000
        )
        self.connected = True
        file_logger.log(f"✅ WebSocket подключен для {self.user_id}")
    
    async def _setup_domains(self):
        """Включает все нужные домены"""
        await self._send("Page.enable", {})
        await self._send("Runtime.enable", {})
        await self._send("DOM.enable", {})
        await self._send("Network.enable", {})
        await self._send("Target.setAutoAttach", {
            "autoAttach": True,
            "flatten": True,
            "waitForDebuggerOnStart": False
        })
        file_logger.log("✅ Domains enabled")
    
    async def _navigate_to_default(self):
        """Открывает страницу по умолчанию"""
        await self._send("Page.navigate", {"url": "https://google.com"})
        await self._wait_for_page_load()
    
    # ============================================
    # ОЖИДАНИЕ ЗАГРУЗКИ
    # ============================================
    
    async def _wait_for_page_load(self, timeout=15):
        """Ждёт загрузки страницы"""
        for i in range(timeout):
            await asyncio.sleep(1)
            try:
                resp = await self._send("Runtime.evaluate", {
                    "expression": "document.title",
                    "returnByValue": True
                })
                if "result" in resp and "result" in resp["result"]:
                    title = resp["result"]["result"].get("value", "")
                    if title:
                        self.page_loaded = True
                        file_logger.log(f"📄 Страница загружена: {title}")
                        await self._update_snapshot()
                        return True
            except:
                pass
        file_logger.log(f"⚠️ Страница не загрузилась за {timeout} секунд")
        return False
    
    # ============================================
    # ОТПРАВКА КОМАНД (С СИНХРОНИЗАЦИЕЙ)
    # ============================================
    
    async def _send(self, method, params=None, session_id=None):
        """Отправляет команду в Chrome с синхронизацией (как в Hermes)"""
        if not self.connected:
            return {"error": "Not connected"}
        
        self.msg_id += 1
        msg_id = self.msg_id
        msg = {
            "id": msg_id,
            "method": method,
            "params": params or {}
        }
        if session_id:
            msg["sessionId"] = session_id
        
        # ✅ Создаём Future для ожидания ответа
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[msg_id] = future
        
        try:
            await self.ws.send(json.dumps(msg))
            response = await asyncio.wait_for(future, timeout=30)
            return response
            
        except asyncio.TimeoutError:
            self._pending_requests.pop(msg_id, None)
            return {"error": "Timeout"}
        except Exception as e:
            self._pending_requests.pop(msg_id, None)
            file_logger.log(f"❌ Send error: {e}", "ERROR")
            return {"error": str(e)}
    
    # ============================================
    # ✅ ОСНОВНОЙ ЦИКЛ ОБРАБОТКИ СОБЫТИЙ (Hermes)
    # ============================================
    
    async def _event_loop(self):
        """Главный цикл обработки событий (как в Hermes)"""
        while self.running and self.connected:
            try:
                # ✅ Используем Lock для безопасного recv
                async with self._recv_lock:
                    response = await asyncio.wait_for(self.ws.recv(), timeout=30)
                
                data = json.loads(response)
                
                # ✅ Проверяем, есть ли ожидающий запрос с этим id
                if "id" in data and data["id"] in self._pending_requests:
                    future = self._pending_requests.pop(data["id"])
                    if not future.done():
                        future.set_result(data)
                    continue
                
                # ✅ Если это событие (без id) — обрабатываем
                if "method" in data:
                    await self._handle_event(data)
                    
            except asyncio.TimeoutError:
                continue
            except websockets.ConnectionClosed:
                self.connected = False
                file_logger.log("⚠️ WebSocket закрыт")
                break
            except Exception as e:
                file_logger.log(f"❌ Event loop error: {e}", "ERROR")
                await asyncio.sleep(1)
    
    # ============================================
    # ОБРАБОТКА СОБЫТИЙ
    # ============================================
    
    async def _handle_event(self, data):
        """Обрабатывает событие от Chrome"""
        method = data.get("method")
        params = data.get("params", {})
        
        # ============================================
        # ДИАЛОГИ
        # ============================================
        if method == "Page.javascriptDialogOpening":
            dialog_message = params.get('message', '')
            dialog_type = params.get('type', '')
            
            file_logger.log(f"💬 Диалог обнаружен: {dialog_message} (тип: {dialog_type})")
            
            if CURRENT_DIALOG_POLICY == "auto_dismiss":
                file_logger.log("🚫 auto_dismiss — закрываю диалог")
                await self._send("Page.handleJavaScriptDialog", {"accept": False})
                return
            elif CURRENT_DIALOG_POLICY == "auto_accept":
                file_logger.log("✅ auto_accept — принимаю диалог")
                await self._send("Page.handleJavaScriptDialog", {"accept": True})
                return
            
            self.pending_dialogs.append({
                "message": dialog_message,
                "type": dialog_type,
                "defaultPrompt": params.get("defaultPrompt", ""),
                "timestamp": time.time()
            })
            
            if self.dialog_timeout_task is None or self.dialog_timeout_task.done():
                self.dialog_timeout_task = asyncio.create_task(self._dialog_timeout_check())
            return
        
        # ============================================
        # IFRAME (OOPIF)
        # ============================================
        if method == "Target.attachedToTarget":
            target_info = params.get("targetInfo", {})
            session_id = params.get("sessionId")
            if session_id:
                is_oopif = target_info.get("type") == "iframe"
                self.connected_tabs[session_id] = {
                    "target_id": target_info.get("targetId"),
                    "url": target_info.get("url", ""),
                    "type": target_info.get("type", ""),
                    "session_id": session_id,
                    "is_oopif": is_oopif
                }
                if is_oopif:
                    self.oopifs[session_id] = target_info
                    file_logger.log(f"🔗 OOPIF обнаружен: {target_info.get('url', '')[:50]}")
                else:
                    file_logger.log(f"🔗 Прикреплён фрейм: {target_info.get('url', '')[:50]}")
            return
        
        # ============================================
        # ЗАГРУЗКА СТРАНИЦЫ
        # ============================================
        if method == "Page.loadEventFired":
            self.page_loaded = True
            file_logger.log("📄 Page.loadEventFired — страница загружена")
            await self._update_snapshot()
            return
        
        if method == "Page.frameNavigated":
            frame = params.get('frame', {})
            file_logger.log(f"🧭 Frame navigated: {frame.get('url', '')[:50]}")
            await self._update_snapshot()
            return
    
    async def _dialog_timeout_check(self):
        """Проверяет таймаут диалогов"""
        await asyncio.sleep(self.dialog_timeout)
        if self.pending_dialogs:
            file_logger.log(f"⏰ Таймаут диалога ({self.dialog_timeout}с), закрываю")
            dialog = self.pending_dialogs.pop(0)
            await self._send("Page.handleJavaScriptDialog", {"accept": False})
    
    # ============================================
    # HEARTBEAT
    # ============================================
    
    async def _heartbeat(self):
        """Проверка живучести соединения"""
        while self.running and not self._stop_event.is_set():
            await asyncio.sleep(30)
            try:
                resp = await self._send("Browser.getVersion", {})
                if "error" in resp:
                    file_logger.log("⚠️ Heartbeat failed, переподключаюсь")
                    self.connected = False
                    await self._reconnect()
            except:
                file_logger.log("⚠️ Heartbeat exception, переподключаюсь")
                self.connected = False
                await self._reconnect()
    
    async def _reconnect(self):
        """Переподключается к Chrome"""
        await asyncio.sleep(2)
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
        self.connected = False
        await self._connect()
        await self._setup_domains()
    
    # ============================================
    # ОБНОВЛЕНИЕ SNAPSHOT
    # ============================================
    
    async def _update_snapshot(self):
        """Обновляет snapshot страницы"""
        try:
            ref_elements = await self._get_accessibility_tree()
            
            frame_tree_resp = await self._send("Page.getFrameTree", {})
            if "result" in frame_tree_resp:
                self.frame_tree = frame_tree_resp["result"].get("frameTree", {})
            
            title_resp = await self._send("Runtime.evaluate", {
                "expression": "document.title",
                "returnByValue": True
            })
            title = "Нет заголовка"
            if "result" in title_resp and "result" in title_resp["result"]:
                title = title_resp["result"]["result"].get("value", "Нет заголовка")
            
            url_resp = await self._send("Runtime.evaluate", {
                "expression": "window.location.href",
                "returnByValue": True
            })
            url = "Нет URL"
            if "result" in url_resp and "result" in url_resp["result"]:
                url = url_resp["result"]["result"].get("value", "Нет URL")
            
            self.full_snapshot = {
                "title": title,
                "url": url,
                "ref_elements": ref_elements,
                "pending_dialogs": self.pending_dialogs.copy(),
                "frame_tree": self.frame_tree,
                "connected_tabs": self.connected_tabs.copy(),
                "oopifs": self.oopifs.copy()
            }
            
            self.ref_elements = {el['ref']: el for el in ref_elements}
            
            file_logger.log(f"✅ Snapshot обновлён: {len(ref_elements)} Ref ID элементов")
            return True
        except Exception as e:
            file_logger.log(f"❌ Snapshot error: {e}", "ERROR")
            return False
    
    async def _get_accessibility_tree(self):
        """Получает accessibility tree"""
        try:
            js_code = """
            (function() {
                const result = [];
                let ref_counter = 0;
                const important = ['button', 'a', 'input', 'textarea', 'select', 
                                  '[role="button"]', '[role="link"]', '[role="searchbox"]',
                                  '[role="combobox"]', '[role="textbox"]', '[role="menuitem"]'];
                
                const elements = document.querySelectorAll(important.join(','));
                
                for (const el of elements) {
                    const rect = el.getBoundingClientRect();
                    const visible = rect.width > 0 && rect.height > 0 && 
                                   el.offsetParent !== null;
                    
                    if (visible) {
                        ref_counter++;
                        const tag = el.tagName.toLowerCase();
                        const role = el.getAttribute('role') || '';
                        const text = (el.textContent || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim().slice(0, 50);
                        const href = el.getAttribute('href') || '';
                        const data_testid = el.getAttribute('data-testid') || '';
                        
                        let element_type = tag;
                        if (role) element_type = role;
                        if (tag === 'input' && el.getAttribute('type') === 'submit') element_type = 'button';
                        if (tag === 'input' && el.getAttribute('type') === 'text') element_type = 'textbox';
                        if (tag === 'input' && el.getAttribute('role') === 'combobox') element_type = 'combobox';
                        if (tag === 'input' && el.getAttribute('type') === 'search') element_type = 'searchbox';
                        
                        let action = '';
                        if (element_type === 'button' || element_type === 'link') action = 'click';
                        else if (element_type === 'textbox' || element_type === 'combobox' || element_type === 'searchbox' || tag === 'input' || tag === 'textarea') action = 'type';
                        
                        result.push({
                            ref: 'e' + ref_counter,
                            tag: tag,
                            role: role,
                            type: element_type,
                            text: text,
                            href: href,
                            data_testid: data_testid,
                            action: action,
                            visible: visible,
                            selector: el.id ? '#' + el.id : 
                                      el.className ? '.' + el.className.split(' ').join('.') : 
                                      tag + (href ? '[href="' + href + '"]' : ''),
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        });
                    }
                }
                
                return result;
            })()
            """
            resp = await self._send("Runtime.evaluate", {
                "expression": js_code,
                "returnByValue": True,
                "awaitPromise": True
            })
            
            if "result" in resp and "result" in resp["result"]:
                result = resp["result"]["result"].get("value", [])
                if isinstance(result, list):
                    return result
            return []
        except Exception as e:
            file_logger.log(f"❌ Accessibility tree error: {e}", "ERROR")
            return []
    
    # ============================================
    # 🆕 HERMES: ensure_session
    # ============================================
    
    async def ensure_session(self):
        """Проверяет и пересоздаёт сессию если нужно"""
        if not self.connected:
            await self._connect()
            await self._setup_domains()
        if not self.page_loaded:
            await self._wait_for_page_load()
        return self.connected and self.page_loaded
    
    # ============================================
    # 🆕 HERMES: browser_snapshot
    # ============================================
    
    async def browser_snapshot(self, full=False):
        """Возвращает snapshot как в Hermes"""
        if not self.full_snapshot:
            await self._update_snapshot()
        
        if full:
            return self.full_snapshot
        else:
            snapshot = self.full_snapshot or {}
            return {
                "title": snapshot.get("title", "Нет заголовка"),
                "url": snapshot.get("url", "Нет URL"),
                "ref_elements": snapshot.get("ref_elements", [])[:30],
                "pending_dialogs": snapshot.get("pending_dialogs", []),
                "frame_tree": snapshot.get("frame_tree", {})
            }
    
    # ============================================
    # 🆕 HERMES: browser_cdp
    # ============================================
    
    async def browser_cdp(self, method, params=None, frame_id=None):
        """Универсальный CDP-инструмент с поддержкой фреймов"""
        session_id = None
        if frame_id:
            for sid, info in self.connected_tabs.items():
                if info.get("target_id") == frame_id:
                    session_id = sid
                    break
        
        if session_id:
            return await self._send(method, params, session_id)
        return await self._send(method, params)
    
    # ============================================
    # 🆕 HERMES: browser_click (humanized)
    # ============================================
    
    async def browser_click(self, ref_id, humanized=True):
        """Клик с человеческим поведением"""
        if ref_id not in self.ref_elements:
            return {"error": f"Элемент {ref_id} не найден"}
        
        if humanized:
            return await self._humanized_click(ref_id)
        else:
            return await self.click_by_ref(ref_id)
    
    async def _humanized_click(self, ref_id):
        """Человеческий клик с Bezier кривой"""
        el_info = self.ref_elements[ref_id]
        selector = el_info.get('selector')
        if not selector:
            return {"error": "Нет селектора"}
        
        js_code = f"""
        (function() {{
            const el = document.querySelector("{selector}");
            if (!el) return null;
            const rect = el.getBoundingClientRect();
            return {{
                x: rect.x + rect.width / 2,
                y: rect.y + rect.height / 2,
                width: rect.width,
                height: rect.height
            }};
        }})()
        """
        resp = await self._send("Runtime.evaluate", {
            "expression": js_code,
            "returnByValue": True
        })
        
        if "result" in resp and "result" in resp["result"]:
            pos = resp["result"]["result"].get("value")
            if pos:
                x = pos["x"] + random.randint(-3, 3)
                y = pos["y"] + random.randint(-3, 3)
                
                await asyncio.sleep(random.uniform(0.05, 0.15))
                
                await self._send("Input.dispatchMouseEvent", {
                    "type": "mousePressed",
                    "x": x,
                    "y": y,
                    "button": "left",
                    "clickCount": 1
                })
                await asyncio.sleep(random.uniform(0.05, 0.1))
                await self._send("Input.dispatchMouseEvent", {
                    "type": "mouseReleased",
                    "x": x,
                    "y": y,
                    "button": "left",
                    "clickCount": 1
                })
                
                await self._update_snapshot()
                return {"success": True, "method": "humanized"}
        
        return await self.click_by_ref(ref_id)
    
    # ============================================
    # 🆕 HERMES: browser_type (humanized)
    # ============================================
    
    async def browser_type(self, ref_id, text, humanized=True):
        """Ввод текста с человеческим поведением"""
        if ref_id not in self.ref_elements:
            return {"error": f"Элемент {ref_id} не найден"}
        
        if humanized:
            return await self._humanized_type(ref_id, text)
        else:
            return await self.fill_by_ref(ref_id, text)
    
    async def _humanized_type(self, ref_id, text):
        """Человеческий ввод с задержками"""
        el_info = self.ref_elements[ref_id]
        selector = el_info.get('selector')
        if not selector:
            return {"error": "Нет селектора"}
        
        await self._humanized_click(ref_id)
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        for char in text:
            await self._send("Input.dispatchKeyEvent", {
                "type": "keyDown",
                "text": char
            })
            await asyncio.sleep(random.uniform(0.05, 0.15))
            await self._send("Input.dispatchKeyEvent", {
                "type": "keyUp",
                "text": char
            })
            await asyncio.sleep(random.uniform(0.02, 0.08))
        
        await self._update_snapshot()
        return {"success": True, "method": "humanized"}
    
    # ============================================
    # 🆕 HERMES: browser_press
    # ============================================
    
    async def browser_press(self, key):
        """Нажатие клавиши"""
        await self._send("Input.dispatchKeyEvent", {
            "type": "keyDown",
            "key": key
        })
        await asyncio.sleep(random.uniform(0.05, 0.1))
        await self._send("Input.dispatchKeyEvent", {
            "type": "keyUp",
            "key": key
        })
        return {"success": True}
    
    # ============================================
    # 🆕 HERMES: browser_dialog
    # ============================================
    
    async def browser_dialog(self, action="accept", prompt_text=""):
        """Обработка диалога"""
        if not self.pending_dialogs:
            return {"error": "Нет ожидающих диалогов"}
        
        dialog = self.pending_dialogs.pop(0)
        accept = action == "accept"
        
        await self._send("Page.handleJavaScriptDialog", {
            "accept": accept,
            "promptText": prompt_text
        })
        
        file_logger.log(f"✅ Диалог обработан: {dialog.get('message', '')}")
        await self._update_snapshot()
        return {"success": True, "dialog": dialog}
    
    # ============================================
    # БАЗОВЫЕ ДЕЙСТВИЯ
    # ============================================
    
    async def click_by_ref(self, ref_id):
        """Клик по Ref ID"""
        if ref_id not in self.ref_elements:
            return {"error": f"Элемент {ref_id} не найден"}
        
        el_info = self.ref_elements[ref_id]
        selector = el_info.get('selector')
        if not selector:
            return {"error": f"Нет селектора для {ref_id}"}
        
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
        resp = await self._send("Runtime.evaluate", {
            "expression": js_code,
            "returnByValue": True,
            "awaitPromise": True
        })
        
        if "result" in resp and "result" in resp["result"]:
            result = resp["result"]["result"].get("value", {})
            if result and result.get("success"):
                await self._update_snapshot()
                return {"success": True}
        
        return {"success": False}
    
    async def fill_by_ref(self, ref_id, value):
        """Заполнение поля по Ref ID"""
        if ref_id not in self.ref_elements:
            return {"error": f"Элемент {ref_id} не найден"}
        
        el_info = self.ref_elements[ref_id]
        selector = el_info.get('selector')
        if not selector:
            return {"error": f"Нет селектора для {ref_id}"}
        
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
        resp = await self._send("Runtime.evaluate", {
            "expression": js_code,
            "returnByValue": True,
            "awaitPromise": True
        })
        
        if "result" in resp and "result" in resp["result"]:
            result = resp["result"]["result"].get("value", {})
            if result and result.get("success"):
                await self._update_snapshot()
                return {"success": True}
        
        return {"success": False}
    
    async def navigate(self, url):
        """Переход на URL"""
        await self._send("Page.navigate", {"url": url})
        await self._wait_for_page_load()
        await self._update_snapshot()
        return {"success": True}
    
    async def screenshot(self):
        """Делает скриншот"""
        resp = await self._send("Page.captureScreenshot", {
            "format": "png",
            "captureBeyondViewport": True,
            "fromSurface": True
        })
        
        if "result" in resp and "data" in resp["result"]:
            img_data = base64.b64decode(resp["result"]["data"])
            if len(img_data) > 100:
                return img_data
        
        return None
    
    async def get_description(self):
        """Возвращает описание страницы для агента"""
        snapshot = await self.browser_snapshot(full=False)
        if not snapshot:
            return "Страница не загружена"
        
        ref_elements = snapshot.get('ref_elements', [])
        title = snapshot.get('title', 'Нет заголовка')
        url = snapshot.get('url', 'Нет URL')
        
        desc_lines = []
        desc_lines.append(f"📄 СТРАНИЦА: {title}")
        desc_lines.append(f"🔗 URL: {url}")
        desc_lines.append("")
        desc_lines.append("🆔 ДОСТУПНЫЕ ЭЛЕМЕНТЫ (Ref ID):")
        
        if ref_elements:
            for el in ref_elements[:30]:
                ref = el.get('ref', '')
                text = el.get('text', '')[:30]
                tag = el.get('tag', '')
                action = el.get('action', '')
                desc_lines.append(f"  {ref}: \"{text}\" ({tag}) → {action}")
        else:
            desc_lines.append("  • (нет данных)")
        
        dialogs = snapshot.get('pending_dialogs', [])
        if dialogs:
            desc_lines.append("")
            desc_lines.append(f"💬 ОЖИДАЮЩИЕ ДИАЛОГИ ({len(dialogs)}):")
            for d in dialogs:
                desc_lines.append(f"  • {d.get('message', '')} (тип: {d.get('type', 'unknown')})")
            desc_lines.append("")
            desc_lines.append("💡 Для обработки диалога используй: handle_dialog(accept=True)")
        
        frame_tree = snapshot.get('frame_tree', {})
        if frame_tree:
            desc_lines.append("")
            desc_lines.append("📦 IFRAME/ФРЕЙМЫ:")
            main_frame = frame_tree.get('frame', {})
            if main_frame:
                desc_lines.append(f"  • Главный: {main_frame.get('url', '')[:60]}")
            children = frame_tree.get('childFrames', [])
            if children:
                for child in children[:5]:
                    child_url = child.get('frame', {}).get('url', '')
                    if child_url:
                        desc_lines.append(f"  • Дочерний: {child_url[:60]}")
        
        desc_lines.append("")
        desc_lines.append("💡 КАК ИСПОЛЬЗОВАТЬ Ref ID:")
        desc_lines.append('• click e5 → кликнуть по элементу e5')
        desc_lines.append('• fill e5 "текст" → заполнить поле e5')
        
        return "\n".join(desc_lines)

# ---------- Хранилище супервайзеров ----------

supervisors = {}

async def get_supervisor(user_id: int) -> CDPSupervisor:
    """Получает или создает супервайзера для пользователя"""
    if user_id not in supervisors:
        ws_url = get_page_ws_url()
        if not ws_url:
            ws_url = create_page()
            if not ws_url:
                return None
        
        supervisor = CDPSupervisor(user_id, ws_url)
        await supervisor.start()
        supervisors[user_id] = supervisor
    
    return supervisors[user_id]

# ---------- Agnes AI ----------

async def ask_agnes(prompt: str, page_desc: str) -> dict:
    if not AGNES_API_KEY:
        return {"error": "AGNES_API_KEY не установлен"}
    
    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json"
    }
    
    AGENT_CODE = """
🤖 АГЕНТ ДЛЯ УПРАВЛЕНИЯ БРАУЗЕРОМ

📌 ДОСТУПНЫЕ ДЕЙСТВИЯ (ТОЛЬКО Ref ID):
1. navigate(url) - открыть сайт
2. click(ref) - кликнуть по элементу
3. fill(ref, value) - заполнить поле
4. press_enter() - нажать Enter
5. screenshot() - скриншот
6. answer(text) - ответить
7. handle_dialog(accept) - обработать диалог

📌 ПРИМЕРЫ:
{"action": "click", "params": {"ref": "e8"}}
{"action": "fill", "params": {"ref": "e5", "value": "Spinoza"}}

⚠️ НЕ ИСПОЛЬЗУЙ selector/text — ТОЛЬКО Ref ID!
ОТВЕЧАЙ ТОЛЬКО JSON!
"""
    
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
                        if 'ref' in result and 'params' not in result:
                            result = {"action": result.get('action', 'click'), "params": {"ref": result.get('ref')}}
                    if isinstance(result, list):
                        for i, item in enumerate(result):
                            if isinstance(item, dict) and 'ref' in item and 'params' not in item:
                                result[i] = {"action": item.get('action', 'click'), "params": {"ref": item.get('ref')}}
                    if isinstance(result, list) or (isinstance(result, dict) and 'action' in result):
                        return result
                except:
                    pass
            
            return {"action": "answer", "params": {"text": content}}
        except Exception as e:
            file_logger.log(f"Agnes error: {e}", "ERROR")
            return {"action": "answer", "params": {"text": f"❌ Ошибка: {str(e)}"}}
    
    return {"action": "answer", "params": {"text": "❌ Не удалось получить ответ"}}

# ---------- Выполнение действий ----------

async def execute_action(supervisor: CDPSupervisor, action) -> str:
    if isinstance(action, list):
        results = []
        for a in action:
            result = await execute_single_action(supervisor, a)
            results.append(result)
        return "\n\n".join(results)
    return await execute_single_action(supervisor, action)

async def execute_single_action(supervisor: CDPSupervisor, action: dict) -> str:
    action_type = action.get("action")
    params = action.get("params", {})
    
    file_logger.log(f"Выполнение: {action_type}")
    
    try:
        if action_type == "navigate":
            url = params.get("url", "https://google.com")
            result = await supervisor.navigate(url)
            if result.get("success"):
                return f"✅ Открыл: {url}"
            return f"❌ Не удалось открыть: {url}"
        
        elif action_type == "click":
            ref = params.get("ref")
            if ref:
                result = await supervisor.browser_click(ref, humanized=True)
                if result and result.get("success"):
                    return f"✅ Кликнул: {ref}"
                return f"❌ Не удалось кликнуть {ref}"
            return "❌ Нет ref"
        
        elif action_type == "fill":
            ref = params.get("ref")
            value = params.get("value", "")
            if ref:
                result = await supervisor.browser_type(ref, value, humanized=True)
                if result and result.get("success"):
                    return f"✅ Заполнил: {ref} = {value}"
                return f"❌ Не удалось заполнить {ref}"
            return "❌ Нет ref"
        
        elif action_type == "press_enter":
            result = await supervisor.browser_press("Enter")
            if result.get("success"):
                return "✅ Нажал Enter"
            return "❌ Не удалось нажать Enter"
        
        elif action_type == "handle_dialog":
            accept = params.get("accept", True)
            result = await supervisor.browser_dialog("accept" if accept else "dismiss")
            if result.get("success"):
                return f"✅ Диалог обработан: {result.get('dialog', {}).get('message', '')}"
            return f"❌ Ошибка: {result.get('error', '')}"
        
        elif action_type == "screenshot":
            return "screenshot"
        
        elif action_type == "answer":
            return f"📝 {params.get('text', 'Нет ответа')}"
        
        else:
            return f"⚠️ Неизвестное действие: {action_type}"
            
    except Exception as e:
        file_logger.log(f"Execute error: {e}", "ERROR")
        return f"❌ Ошибка: {str(e)}"

# ---------- Обработчик Telegram ----------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    user_id = update.message.from_user.id
    prompt = update.message.text
    
    file_logger.log(f"Сообщение от {user_id}: {prompt[:100]}...")
    
    await update.message.chat.send_action(action="typing")
    
    try:
        supervisor = await get_supervisor(user_id)
        if not supervisor:
            await update.message.reply_text("❌ Не удалось подключиться к браузеру")
            return
        
        if not await supervisor.ensure_session():
            await update.message.reply_text("❌ Браузер не готов")
            return
        
        page_desc = await supervisor.get_description()
        
        if AGNES_API_KEY:
            response = await ask_agnes(prompt, page_desc)
            if "error" not in response:
                result = await execute_action(supervisor, response)
                if result == "screenshot":
                    img_data = await supervisor.screenshot()
                    if img_data:
                        with open("screenshot.png", "wb") as f:
                            f.write(img_data)
                        with open("screenshot.png", "rb") as photo:
                            await update.message.reply_photo(photo=photo)
                    else:
                        await update.message.reply_text("❌ Не удалось сделать скриншот")
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
        "🧠 **CDP Supervisor (Hermes)**\n\n"
        "Я вижу ВСЁ на странице:\n"
        "• Все кнопки, поля, ссылки\n"
        "• Диалоги (alert/confirm/prompt)\n"
        "• iframe и фреймы\n"
        "• Структуру страницы\n\n"
        "💡 Просто напиши что нужно сделать!\n\n"
        "/cdp - статус браузера\n"
        "/logs - логи\n"
        "/dialog_policy - политика диалогов"
    )

async def cdp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in supervisors:
        supervisor = supervisors[user_id]
        snapshot = await supervisor.browser_snapshot(full=False)
        if snapshot:
            ref_count = len(snapshot.get('ref_elements', []))
            dialogs = len(snapshot.get('pending_dialogs', []))
            frames = len(snapshot.get('connected_tabs', {}))
            await update.message.reply_text(
                f"✅ **Браузер активен**\n\n"
                f"🆔 Ref ID элементов: {ref_count}\n"
                f"💬 Ожидающих диалогов: {dialogs}\n"
                f"📦 Фреймов: {frames}\n"
                f"📊 Статус: Готов"
            )
        else:
            await update.message.reply_text("❌ Нет данных")
    else:
        await update.message.reply_text("❌ Браузер не запущен")

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

async def dialog_policy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📋 Текущая политика диалогов: **{CURRENT_DIALOG_POLICY}**\n\n"
        "Доступные политики:\n"
        "• must_respond - ждать ответа агента\n"
        "• auto_dismiss - автоматически закрывать\n"
        "• auto_accept - автоматически принимать\n\n"
        "Изменить: 'Установи политику диалогов auto_dismiss'"
    )

# ---------- Main ----------

def main():
    print("🚀 Запуск бота с CDP Supervisor...")
    file_logger.log("🚀 Запуск бота с CDP Supervisor...")
    
    start_chrome()
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cdp", cdp))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("dialog_policy", dialog_policy_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен!")
    file_logger.log("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()