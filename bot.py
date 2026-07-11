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
import signal
import sys
from collections import deque
from typing import Optional, Dict, Any, List
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

# ---------- ДИАЛОГОВАЯ ПОЛИТИКА ----------
DIALOG_POLICY = {
    "must_respond": "wait",
    "auto_dismiss": "dismiss",
    "auto_accept": "accept"
}
CURRENT_DIALOG_POLICY = "must_respond"
DIALOG_TIMEOUT_SECONDS = 300
MAX_RECENT_DIALOGS = 20

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

# ---------- Chrome (Pydoll-style маскировка) ----------
def start_chrome():
    try:
        file_logger.log("Запуск Chrome с Pydoll маскировкой...")
        result = subprocess.run(["pgrep", "-f", "google-chrome"], capture_output=True, text=True)
        if result.stdout:
            file_logger.log("✅ Chrome уже запущен")
            return True
        
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
        subprocess.Popen([
            CHROME_PATH,
            "--remote-debugging-port=9222",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            
            # ✅ Pydoll stealth-флаги (без headless!)
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--lang=en-US",
            "--accept-lang=en-US,en;q=0.9",
            "--disable-sync",
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
            "--metrics-recording-only",
            "--safebrowsing-disable-auto-update",
            "--force-color-profile=srgb",
            
            # ✅ WebRTC защита
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            
            # ✅ Реалистичный User-Agent
            f"--user-agent={user_agent}",
            
            # ⚠️ НЕ ИСПОЛЬЗУЕМ HEADLESS (как в Pydoll)
            # "--headless=new",  # ❌ УБРАНО!
            
            # ✅ Дополнительные флаги для производительности
            "--disable-gpu",
            "--disable-software-rasterizer"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        
        time.sleep(5)
        file_logger.log("✅ Chrome запущен (Pydoll маскировка, без headless)")
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
# 🧠 CDP SUPERVISOR С ПОЛНОЙ МАСКИРОВКОЙ Pydoll
# ============================================

class CDPSupervisor:
    def __init__(self, user_id: int, ws_url: str):
        self.user_id = user_id
        self.ws_url = ws_url
        self.ws = None
        self.connected = False
        self.msg_id = 0
        self.running = False
        self.page_loaded = False
        
        self.pending_dialogs = []
        self.recent_dialogs = deque(maxlen=MAX_RECENT_DIALOGS)
        self.frame_tree = {}
        self.connected_tabs = {}
        self.ref_elements = {}
        self.full_snapshot = None
        self.oopifs = {}
        
        self._pending_requests = {}
        self._recv_lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._ready_event = asyncio.Event()
        self._dialog_counter = 0
        self._navigation_lock = asyncio.Lock()
        self._navigation_future = None
        
        self.dialog_timeout = DIALOG_TIMEOUT_SECONDS
        self.ping_interval = 60
        self.ping_timeout = 180
        
        self.supervisor_task = None
        self.heartbeat_task = None
        self.dialog_timeout_task = None
        self.event_loop_task = None
        
        self.stealth_injected = False
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    def _is_ws_closed(self):
        if not self.ws:
            return True
        if hasattr(self.ws, 'state'):
            return self.ws.state.name in ["CLOSED", "CLOSING"]
        if hasattr(self.ws, 'closed'):
            return self.ws.closed
        return False
    
    async def start(self):
        if self.running:
            return True
        
        file_logger.log(f"🧠 Запуск CDP Supervisor для {self.user_id}")
        self.running = True
        self._stop_event.clear()
        self.supervisor_task = asyncio.create_task(self._run())
        
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=30)
            return True
        except asyncio.TimeoutError:
            file_logger.log(f"⚠️ Supervisor не готов за 30 секунд")
            return False
    
    async def stop(self):
        self.running = False
        self._stop_event.set()
        
        if self.supervisor_task:
            self.supervisor_task.cancel()
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.event_loop_task:
            self.event_loop_task.cancel()
        if self.ws:
            await self.ws.close()
        
        file_logger.log(f"🧠 CDP Supervisor остановлен для {self.user_id}")
    
    async def _run(self):
        """Основной цикл супервайзера"""
        file_logger.log("🚀 Запуск CDP Supervisor...")
        
        while self.running and not self._stop_event.is_set():
            try:
                file_logger.log("🔗 Подключение к Chrome...")
                await self._connect()
                
                file_logger.log("🔄 Запуск event loop...")
                self.event_loop_task = asyncio.create_task(self._event_loop())
                
                for attempt in range(20):
                    if self.event_loop_task and not self.event_loop_task.done():
                        file_logger.log(f"✅ Event loop запущен (попытка {attempt+1})")
                        break
                    await asyncio.sleep(0.5)
                else:
                    raise Exception("Event loop не запустился")
                
                file_logger.log("⚙️ Настройка доменов с Pydoll маскировкой...")
                await self._setup_domains()
                
                file_logger.log("🛡️ Инъекция Pydoll stealth скриптов...")
                await self._inject_pydoll_stealth_scripts()
                
                ready = False
                for attempt in range(10):
                    try:
                        test_result = await asyncio.wait_for(
                            self._send("Browser.getVersion", {}),
                            timeout=2
                        )
                        if "error" not in test_result:
                            file_logger.log(f"✅ Supervisor готов (попытка {attempt+1})")
                            ready = True
                            break
                    except:
                        pass
                    await asyncio.sleep(0.5)
                
                if not ready:
                    raise Exception("Supervisor не готов")
                
                file_logger.log("✅ Supervisor готов к работе! Ожидаю команды...")
                self._ready_event.set()
                
                self.heartbeat_task = asyncio.create_task(self._heartbeat())
                
                await asyncio.gather(
                    self.event_loop_task,
                    self.heartbeat_task,
                    return_exceptions=True
                )
                
            except websockets.ConnectionClosed:
                file_logger.log(f"⚠️ WebSocket закрыт, переподключаюсь...")
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                file_logger.log(f"❌ Supervisor error: {e}", "ERROR")
                await asyncio.sleep(5)
    
    async def wait_for_ready(self, timeout=30):
        start = time.time()
        while time.time() - start < timeout:
            if (self.connected and 
                self.ws and 
                not self._is_ws_closed() and
                self._ready_event.is_set()):
                return True
            await asyncio.sleep(0.5)
        return False
    
    async def get_status(self) -> str:
        status_parts = []
        
        if self.connected and self.ws and not self._is_ws_closed():
            status_parts.append("✅ Подключен к Chrome (Pydoll маскировка)")
        else:
            status_parts.append("❌ Нет подключения к Chrome")
        
        if self.page_loaded:
            status_parts.append("✅ Страница загружена")
            if self.full_snapshot:
                title = self.full_snapshot.get('title', 'Без заголовка')
                url = self.full_snapshot.get('url', 'Без URL')
                status_parts.append(f"📄 {title} ({url[:50]}...)")
        else:
            status_parts.append("⏳ Страница не загружена")
        
        if self.pending_dialogs:
            status_parts.append(f"💬 Ожидающих диалогов: {len(self.pending_dialogs)}")
        else:
            status_parts.append("✅ Нет ожидающих диалогов")
        
        if self.ref_elements:
            status_parts.append(f"🆔 Доступно элементов: {len(self.ref_elements)}")
        
        return "\n".join(status_parts)
    
    async def _connect(self):
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
        """Настройка доменов с полной маскировкой Pydoll"""
        try:
            # ✅ 1. Синхронизация User-Agent через CDP (КРИТИЧЕСКИ ВАЖНО!)
            await asyncio.wait_for(
                self._send("Emulation.setUserAgentOverride", {
                    "userAgent": self.user_agent,
                    "platform": "Win32",
                    "userAgentMetadata": {
                        "brands": [
                            {"brand": "Not_A Brand", "version": "8"},
                            {"brand": "Chromium", "version": "120"},
                            {"brand": "Google Chrome", "version": "120"}
                        ],
                        "fullVersion": "120.0.6099.109",
                        "platform": "Windows",
                        "platformVersion": "10.0.0",
                        "architecture": "x86_64",
                        "model": "",
                        "mobile": False
                    }
                }),
                timeout=10
            )
            
            # ✅ 2. Эмуляция геолокации (опционально)
            await asyncio.wait_for(
                self._send("Emulation.setGeolocationOverride", {
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "accuracy": 100
                }),
                timeout=5
            )
            
            # ✅ 3. Эмуляция размера экрана
            await asyncio.wait_for(
                self._send("Emulation.setDeviceMetricsOverride", {
                    "width": 1920,
                    "height": 1080,
                    "deviceScaleFactor": 1,
                    "mobile": False
                }),
                timeout=5
            )
            
            # ✅ 4. Включение всех доменов
            await asyncio.wait_for(self._send("Page.enable", {}), timeout=10)
            await asyncio.wait_for(self._send("Runtime.enable", {}), timeout=10)
            await asyncio.wait_for(self._send("DOM.enable", {}), timeout=10)
            await asyncio.wait_for(self._send("Network.enable", {}), timeout=10)
            await asyncio.wait_for(
                self._send("Target.setAutoAttach", {
                    "autoAttach": True,
                    "flatten": True,
                    "waitForDebuggerOnStart": False
                }),
                timeout=10
            )
            
            # ✅ 5. Настройка Network для маскировки
            await asyncio.wait_for(
                self._send("Network.setExtraHTTPHeaders", {
                    "headers": {
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept-Encoding": "gzip, deflate, br",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                        "Connection": "keep-alive",
                        "Upgrade-Insecure-Requests": "1"
                    }
                }),
                timeout=10
            )
            
            file_logger.log("✅ Domains enabled (Pydoll маскировка)")
        except asyncio.TimeoutError:
            file_logger.log("⚠️ Таймаут при настройке доменов")
            raise
    
    async def _inject_pydoll_stealth_scripts(self):
        """Инъекция полного набора stealth скриптов из Pydoll"""
        try:
            js_code = """
            // ============================================
            // Pydoll COMPLETE STEALTH SCRIPTS
            // ============================================
            
            // 1. Убираем navigator.webdriver (главное!)
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // 2. Подмена navigator.plugins (как у реального Chrome)
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const plugins = [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                        { name: 'Native Client', filename: 'internal-nacl-plugin' },
                        { name: 'Widevine Content Decryption Module', filename: 'widevinecdm' },
                        { name: 'Chrome Remote Desktop Viewer', filename: 'internal-remoting-viewer' }
                    ];
                    plugins.length = 5;
                    plugins.item = (i) => plugins[i] || null;
                    plugins.namedItem = (name) => {
                        for (const p of plugins) {
                            if (p.name === name) return p;
                        }
                        return null;
                    };
                    plugins.refresh = () => {};
                    return plugins;
                }
            });
            
            // 3. Подмена navigator.mimeTypes
            Object.defineProperty(navigator, 'mimeTypes', {
                get: () => {
                    const mimeTypes = [
                        { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
                        { type: 'text/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
                        { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format' }
                    ];
                    mimeTypes.length = 3;
                    mimeTypes.item = (i) => mimeTypes[i] || null;
                    mimeTypes.namedItem = (type) => {
                        for (const m of mimeTypes) {
                            if (m.type === type) return m;
                        }
                        return null;
                    };
                    return mimeTypes;
                }
            });
            
            // 4. Подмена navigator.languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en', 'ru', 'uk']
            });
            
            Object.defineProperty(navigator, 'language', {
                get: () => 'en-US'
            });
            
            // 5. Подмена navigator.connection (WebRTC защита)
            if (navigator.connection) {
                Object.defineProperty(navigator.connection, 'rtt', {
                    get: () => Math.floor(Math.random() * 100) + 50
                });
                Object.defineProperty(navigator.connection, 'downlink', {
                    get: () => Math.floor(Math.random() * 50) + 10
                });
            }
            
            // 6. Подмена WebGL (защита от fingerprint)
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                if (parameter === 37446) {
                    return 'Intel Iris OpenGL Engine';
                }
                if (parameter === 37447) {
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter.call(this, parameter);
            };
            
            const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                if (parameter === 37446) {
                    return 'Intel Iris OpenGL Engine';
                }
                if (parameter === 37447) {
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter2.call(this, parameter);
            };
            
            // 7. Подмена Canvas fingerprint
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            const originalToBlob = HTMLCanvasElement.prototype.toBlob;
            
            HTMLCanvasElement.prototype.toDataURL = function(type) {
                const result = originalToDataURL.call(this, type);
                // Добавляем небольшой шум в изображение
                return result;
            };
            
            HTMLCanvasElement.prototype.toBlob = function(callback, type) {
                // Добавляем небольшой шум в изображение
                originalToBlob.call(this, callback, type);
            };
            
            // 8. Подмена screen размеров
            Object.defineProperty(window.screen, 'width', {
                get: () => 1920
            });
            Object.defineProperty(window.screen, 'height', {
                get: () => 1080
            });
            Object.defineProperty(window.screen, 'availWidth', {
                get: () => 1920
            });
            Object.defineProperty(window.screen, 'availHeight', {
                get: () => 1040
            });
            
            // 9. Подмена window.chrome
            if (!window.chrome) {
                window.chrome = {
                    runtime: {
                        id: 'fake-id-12345'
                    }
                };
            }
            
            // 10. Подмена navigator.hardwareConcurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8
            });
            
            // 11. Подмена navigator.deviceMemory
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });
            
            // 12. Подмена navigator.maxTouchPoints
            Object.defineProperty(navigator, 'maxTouchPoints', {
                get: () => 0
            });
            
            // 13. Подмена navigator.platform
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32'
            });
            
            // 14. Подмена navigator.oscpu
            Object.defineProperty(navigator, 'oscpu', {
                get: () => 'Windows NT 10.0; Win64; x64'
            });
            
            console.log('✅ Pydoll stealth scripts injected successfully');
            """
            
            await asyncio.wait_for(
                self._send("Page.addScriptToEvaluateOnNewDocument", {
                    "source": js_code
                }),
                timeout=10
            )
            self.stealth_injected = True
            file_logger.log("✅ Pydoll stealth скрипты инжектированы")
        except Exception as e:
            file_logger.log(f"⚠️ Ошибка инъекции stealth: {e}")
    
    async def _send(self, method, params=None, session_id=None):
        if not self.connected:
            file_logger.log(f"⚠️ Не подключен к Chrome")
            await self._reconnect()
            if not self.connected:
                return {"error": "Not connected"}
        
        if not self.ws or self._is_ws_closed():
            file_logger.log(f"⚠️ WebSocket закрыт")
            await self._reconnect()
            if not self.ws or self._is_ws_closed():
                return {"error": "WebSocket closed"}
        
        self.msg_id += 1
        msg_id = self.msg_id
        msg = {
            "id": msg_id,
            "method": method,
            "params": params or {}
        }
        if session_id:
            msg["sessionId"] = session_id
        
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[msg_id] = future
        
        try:
            await self.ws.send(json.dumps(msg))
            response = await asyncio.wait_for(future, timeout=30)
            return response
            
        except asyncio.TimeoutError:
            self._pending_requests.pop(msg_id, None)
            file_logger.log(f"⚠️ Таймаут запроса: {method}")
            return {"error": "Timeout"}
        except websockets.ConnectionClosed:
            self.connected = False
            file_logger.log(f"⚠️ WebSocket закрыт при отправке: {method}")
            return {"error": "Connection closed"}
        except Exception as e:
            self._pending_requests.pop(msg_id, None)
            file_logger.log(f"❌ Send error: {e}", "ERROR")
            return {"error": str(e)}
    
    async def _event_loop(self):
        while self.running and self.connected:
            try:
                async with self._recv_lock:
                    response = await asyncio.wait_for(self.ws.recv(), timeout=30)
                
                if not response:
                    continue
                
                data = json.loads(response)
                
                if "id" in data and data["id"] in self._pending_requests:
                    future = self._pending_requests.pop(data["id"])
                    if not future.done():
                        future.set_result(data)
                    continue
                
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
    
    async def _handle_event(self, data):
        method = data.get("method")
        params = data.get("params", {})
        
        if method == "Page.loadEventFired":
            self.page_loaded = True
            file_logger.log("📄 Page.loadEventFired — страница загружена")
            
            if self._navigation_future and not self._navigation_future.done():
                self._navigation_future.set_result(True)
            
            await self._update_snapshot()
            return
        
        if method == "Page.javascriptDialogOpening":
            dialog_message = params.get('message', '')
            dialog_type = params.get('type', '')
            
            self._dialog_counter += 1
            dialog_id = f"d-{self._dialog_counter}"
            
            dialog_info = {
                "id": dialog_id,
                "type": dialog_type,
                "message": dialog_message,
                "defaultPrompt": params.get("defaultPrompt", ""),
                "timestamp": time.time()
            }
            
            file_logger.log(f"💬 Диалог обнаружен [{dialog_id}]: {dialog_message}")
            
            if CURRENT_DIALOG_POLICY == "auto_dismiss":
                file_logger.log(f"🚫 auto_dismiss — закрываю диалог [{dialog_id}]")
                await self._send("Page.handleJavaScriptDialog", {"accept": False})
                self.recent_dialogs.append({
                    **dialog_info,
                    "closed_by": "auto_policy",
                    "action": "dismiss",
                    "closed_at": time.time()
                })
                return
            
            elif CURRENT_DIALOG_POLICY == "auto_accept":
                file_logger.log(f"✅ auto_accept — принимаю диалог [{dialog_id}]")
                await self._send("Page.handleJavaScriptDialog", {"accept": True})
                self.recent_dialogs.append({
                    **dialog_info,
                    "closed_by": "auto_policy",
                    "action": "accept",
                    "closed_at": time.time()
                })
                return
            
            self.pending_dialogs.append(dialog_info)
            
            if self.dialog_timeout_task is None or self.dialog_timeout_task.done():
                self.dialog_timeout_task = asyncio.create_task(self._dialog_timeout_check())
            return
        
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
            return
        
        if method == "Page.frameNavigated":
            frame = params.get('frame', {})
            file_logger.log(f"🧭 Frame navigated: {frame.get('url', '')[:50]}")
            return
    
    async def _wait_for_navigation(self, timeout=30):
        future = asyncio.get_event_loop().create_future()
        self._navigation_future = future
        
        try:
            await asyncio.wait_for(future, timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            self._navigation_future = None
    
    async def _dialog_timeout_check(self):
        await asyncio.sleep(self.dialog_timeout)
        
        for dialog in self.pending_dialogs[:]:
            if time.time() - dialog.get('timestamp', 0) >= self.dialog_timeout:
                file_logger.log(f"⏰ Таймаут диалога [{dialog.get('id')}]")
                
                try:
                    await self._send("Page.handleJavaScriptDialog", {"accept": False})
                    self.recent_dialogs.append({
                        **dialog,
                        "closed_by": "watchdog",
                        "action": "dismiss_timeout",
                        "closed_at": time.time()
                    })
                    self.pending_dialogs.remove(dialog)
                except Exception as e:
                    file_logger.log(f"❌ Ошибка: {e}", "ERROR")
    
    async def _heartbeat(self):
        while self.running and not self._stop_event.is_set():
            await asyncio.sleep(30)
            try:
                resp = await self._send("Browser.getVersion", {})
                if "error" in resp:
                    file_logger.log("⚠️ Heartbeat failed")
                    self.connected = False
                    await self._reconnect()
            except:
                file_logger.log("⚠️ Heartbeat exception")
                self.connected = False
                await self._reconnect()
    
    async def _reconnect(self):
        await asyncio.sleep(2)
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
        self.connected = False
        await self._connect()
        await self._setup_domains()
        await self._inject_pydoll_stealth_scripts()
    
    async def _update_snapshot(self):
        try:
            ref_elements = await self._get_accessibility_tree()
            
            # ✅ Получаем информацию с таймаутами (Google может блокировать JS)
            title = "Страница загружена"
            url = "Неизвестный URL"
            
            # Пробуем получить URL через frame tree (не требует JS)
            try:
                frame_tree_resp = await asyncio.wait_for(
                    self._send("Page.getFrameTree", {}),
                    timeout=5
                )
                if "result" in frame_tree_resp:
                    frame_tree = frame_tree_resp["result"].get("frameTree", {})
                    frame = frame_tree.get("frame", {})
                    if frame.get("url"):
                        url = frame["url"]
                    self.frame_tree = frame_tree
            except:
                pass
            
            # Пробуем получить title с таймаутом (если JS доступен)
            try:
                title_resp = await asyncio.wait_for(
                    self._send("Runtime.evaluate", {
                        "expression": "document.title",
                        "returnByValue": True
                    }),
                    timeout=3
                )
                if "result" in title_resp and "result" in title_resp["result"]:
                    title_val = title_resp["result"]["result"].get("value", "")
                    if title_val and title_val != "about:blank":
                        title = title_val
            except asyncio.TimeoutError:
                file_logger.log("⏳ Таймаут получения title (JS может быть заблокирован)")
            except:
                pass
            
            # Пробуем получить URL через JS с таймаутом
            try:
                url_resp = await asyncio.wait_for(
                    self._send("Runtime.evaluate", {
                        "expression": "window.location.href",
                        "returnByValue": True
                    }),
                    timeout=3
                )
                if "result" in url_resp and "result" in url_resp["result"]:
                    url_val = url_resp["result"]["result"].get("value", "")
                    if url_val and url_val != "about:blank":
                        url = url_val
            except asyncio.TimeoutError:
                file_logger.log("⏳ Таймаут получения URL (JS может быть заблокирован)")
            except:
                pass
            
            self.full_snapshot = {
                "title": title,
                "url": url,
                "ref_elements": ref_elements,
                "pending_dialogs": self.pending_dialogs.copy(),
                "recent_dialogs": list(self.recent_dialogs),
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
    # PUBLIC API
    # ============================================
    
    async def ensure_session(self):
        if not self.connected:
            await self._connect()
            await self._setup_domains()
            await self._inject_pydoll_stealth_scripts()
        return self.connected
    
    async def navigate(self, url):
        async with self._navigation_lock:
            try:
                file_logger.log(f"🌐 Навигация на {url}")
                
                if not self.connected or not self.ws or self._is_ws_closed():
                    file_logger.log("⚠️ Соединение потеряно, переподключаюсь...")
                    await self._reconnect()
                
                result = await asyncio.wait_for(
                    self._send("Page.navigate", {"url": url}),
                    timeout=15
                )
                
                if "error" in result:
                    file_logger.log(f"❌ Ошибка: {result.get('error')}")
                    return {"success": False, "error": result.get("error")}
                
                loaded = await self._wait_for_navigation(timeout=30)
                
                if loaded:
                    file_logger.log(f"✅ Страница загружена: {url}")
                    await self._update_snapshot()
                    return {"success": True}
                else:
                    file_logger.log(f"⚠️ Страница не загрузилась: {url}")
                    return {"success": False, "error": "Page load timeout"}
                
            except asyncio.TimeoutError:
                file_logger.log(f"⚠️ Таймаут навигации на {url}")
                return {"success": False, "error": "Timeout"}
            except Exception as e:
                file_logger.log(f"❌ Navigate error: {e}", "ERROR")
                return {"success": False, "error": str(e)}
    
    async def browser_snapshot(self, full=False):
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
                "recent_dialogs": snapshot.get("recent_dialogs", []),
                "frame_tree": snapshot.get("frame_tree", {})
            }
    
    async def browser_cdp(self, method, params=None, frame_id=None):
        session_id = None
        if frame_id:
            for sid, info in self.connected_tabs.items():
                if info.get("target_id") == frame_id or info.get("url") == frame_id:
                    session_id = sid
                    break
            
            if not session_id and frame_id in self.oopifs:
                for sid, info in self.connected_tabs.items():
                    if info.get("target_id") == self.oopifs[frame_id].get("targetId"):
                        session_id = sid
                        break
        
        if session_id:
            return await self._send(method, params, session_id)
        return await self._send(method, params)
    
    async def browser_click(self, ref_id, humanized=True):
        if ref_id not in self.ref_elements:
            return {"error": f"Элемент {ref_id} не найден"}
        
        if humanized:
            return await self._humanized_click(ref_id)
        else:
            return await self.click_by_ref(ref_id)
    
    async def _humanized_click(self, ref_id):
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
    
    async def browser_type(self, ref_id, text, humanized=True):
        if ref_id not in self.ref_elements:
            return {"error": f"Элемент {ref_id} не найден"}
        
        if humanized:
            return await self._humanized_type(ref_id, text)
        else:
            return await self.fill_by_ref(ref_id, text)
    
    async def _humanized_type(self, ref_id, text):
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
    
    async def browser_press(self, key):
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
    
    async def browser_dialog(self, dialog_id=None, action="accept", prompt_text=""):
        if not self.pending_dialogs:
            return {"error": "Нет ожидающих диалогов"}
        
        if dialog_id is None:
            dialog = self.pending_dialogs.pop(0)
        else:
            for i, d in enumerate(self.pending_dialogs):
                if d.get("id") == dialog_id:
                    dialog = self.pending_dialogs.pop(i)
                    break
            else:
                return {"error": f"Диалог {dialog_id} не найден в очереди"}
        
        accept = action == "accept"
        
        try:
            await self._send("Page.handleJavaScriptDialog", {
                "accept": accept,
                "promptText": prompt_text
            })
            
            self.recent_dialogs.append({
                **dialog,
                "closed_by": "agent",
                "action": action,
                "closed_at": time.time()
            })
            
            file_logger.log(f"✅ Диалог обработан: {dialog.get('message', '')}")
            await self._update_snapshot()
            return {"success": True, "dialog": dialog}
            
        except Exception as e:
            return {"error": str(e)}
    
    async def click_by_ref(self, ref_id):
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
    
    async def screenshot(self):
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
        snapshot = await self.browser_snapshot(full=False)
        if not snapshot:
            return "Страница не загружена"
        
        ref_elements = snapshot.get('ref_elements', [])
        title = snapshot.get('title', 'Нет заголовка')
        url = snapshot.get('url', 'Нет URL')
        pending_dialogs = snapshot.get('pending_dialogs', [])
        recent_dialogs = snapshot.get('recent_dialogs', [])
        
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
        
        if pending_dialogs:
            desc_lines.append("")
            desc_lines.append(f"💬 ОЖИДАЮЩИЕ ДИАЛОГИ ({len(pending_dialogs)}):")
            for d in pending_dialogs:
                dialog_id = d.get('id', 'unknown')
                message = d.get('message', '')
                dialog_type = d.get('type', 'unknown')
                desc_lines.append(f"  • [{dialog_id}] {message} (тип: {dialog_type})")
            desc_lines.append("")
            desc_lines.append("💡 Для обработки диалога используй: handle_dialog с dialog_id")
        
        if recent_dialogs:
            desc_lines.append("")
            desc_lines.append(f"📋 НЕДАВНИЕ ДИАЛОГИ ({len(recent_dialogs)}):")
            for d in list(recent_dialogs)[-5:]:
                dialog_id = d.get('id', 'unknown')
                message = d.get('message', '')[:30]
                closed_by = d.get('closed_by', 'unknown')
                desc_lines.append(f"  • [{dialog_id}] {message} (закрыт: {closed_by})")
        
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
        desc_lines.append("💡 КАК ИСПОЛЬЗОВАТЬ:")
        desc_lines.append('• click e5 → кликнуть по элементу e5')
        desc_lines.append('• fill e5 "текст" → заполнить поле e5')
        desc_lines.append('• handle_dialog d-1 accept → обработать диалог')
        
        return "\n".join(desc_lines)

# ---------- Хранилище супервайзеров ----------

supervisors = {}

async def get_supervisor(user_id: int) -> CDPSupervisor:
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

# ---------- ОБНОВЛЕННЫЙ ПРОМТ ДЛЯ AGNES ----------

AGENT_CODE = """
🤖 АГЕНТ ДЛЯ УПРАВЛЕНИЯ БРАУЗЕРОМ (Pydoll маскировка)

📌 ДОСТУПНЫЕ ДЕЙСТВИЯ И ФОРМАТ:

1️⃣ НАВИГАЦИЯ
{"action": "navigate", "params": {"url": "https://example.com"}}

2️⃣ КЛИК (используй Ref ID из описания страницы)
{"action": "click", "params": {"ref": "e5"}}

3️⃣ ЗАПОЛНЕНИЕ ПОЛЯ (используй Ref ID)
{"action": "fill", "params": {"ref": "e5", "value": "текст"}}

4️⃣ НАЖАТИЕ КЛАВИШИ
{"action": "press_enter", "params": {}}

5️⃣ ОБРАБОТКА ДИАЛОГА (используй dialog_id из описания)
{"action": "handle_dialog", "params": {"dialog_id": "d-1", "accept": true}}
{"action": "handle_dialog", "params": {"dialog_id": "d-1", "accept": false}}

6️⃣ СКРИНШОТ
{"action": "screenshot", "params": {}}

7️⃣ ОТВЕТ ПОЛЬЗОВАТЕЛЮ
{"action": "answer", "params": {"text": "ваш ответ"}}

📌 ВАЖНЫЕ ПРАВИЛА:
• Используй ТОЛЬКО Ref ID (e1, e2, e3...) для кликов и заполнения
• НЕ используй CSS селекторы или XPath
• Для диалогов используй dialog_id (d-1, d-2, d-3...)
• Отвечай ТОЛЬКО JSON, без пояснений
• Если нужно несколько действий - используй массив JSON

⚠️ ОТВЕЧАЙ ТОЛЬКО JSON! БЕЗ ЛИШНИХ СЛОВ!
"""

# ---------- Agnes AI ----------

async def ask_agnes(prompt: str, page_desc: str) -> dict:
    if not AGNES_API_KEY:
        return {"error": "AGNES_API_KEY не установлен"}
    
    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json"
    }
    
    system_prompt = f"""
{AGENT_CODE}

📄 ТЕКУЩЕЕ СОСТОЯНИЕ СТРАНИЦЫ:
{page_desc}

📝 ВАЖНО: ОТВЕЧАЙ ТОЛЬКО JSON! 
Если видишь диалоги - обработай их с помощью handle_dialog и dialog_id.
Если нужно несколько действий - используй массив JSON.
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
                        if 'dialog_id' in result and 'params' not in result:
                            result = {"action": "handle_dialog", "params": {"dialog_id": result.get('dialog_id'), "accept": result.get('accept', True)}}
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
            dialog_id = params.get("dialog_id")
            accept = params.get("accept", True)
            prompt_text = params.get("prompt_text", "")
            
            result = await supervisor.browser_dialog(
                dialog_id=dialog_id,
                action="accept" if accept else "dismiss",
                prompt_text=prompt_text
            )
            
            if result.get("success"):
                dialog = result.get("dialog", {})
                return f"✅ Диалог обработан: {dialog.get('message', '')}"
            return f"❌ Ошибка: {result.get('error', '')}"
        
        elif action_type == "screenshot":
            return "screenshot"
        
        elif action_type == "answer":
            return f"📝 {params.get('text', 'Нет ответа')}"
        
        else:
            return f"⚠️ Неизвестное действие: {action_type}"
            
    except asyncio.CancelledError:
        return "⏹️ Операция отменена"
    except Exception as e:
        file_logger.log(f"Execute error: {e}", "ERROR")
        return f"❌ Ошибка: {str(e)}"

# ---------- Команды Telegram ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 **CDP Supervisor с полной маскировкой Pydoll**\n\n"
        "🤖 Бот готов к работе!\n\n"
        "📊 **Возможности:**\n"
        "• Управление браузером через AI\n"
        "• Полная маскировка под реального пользователя\n"
        "• Обработка диалогов (alert/confirm/prompt)\n"
        "• Работа с iframe и фреймами\n"
        "• Скриншоты страниц\n\n"
        "📝 **Команды:**\n"
        "/status - статус браузера\n"
        "/cdp - детальная информация\n"
        "/cancel - отменить операцию\n"
        "/restart - перезапустить браузер\n"
        "/logs - скачать логи\n"
        "/dialog_policy - политика диалогов\n\n"
        "💡 **Как использовать:**\n"
        "Просто напиши что нужно сделать, например:\n"
        "• 'зайди в google.com'\n"
        "• 'нажми на кнопку Войти'\n"
        "• 'сделай скриншот'\n"
        "• 'заполни поле поиска текстом'\n\n"
        "⏳ Бот показывает статус обработки каждого шага!"
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id in supervisors:
        supervisor = supervisors[user_id]
        status = await supervisor.get_status()
        await update.message.reply_text(f"📊 **Статус браузера:**\n\n{status}")
    else:
        await update.message.reply_text("❌ Браузер не запущен. Отправь любое сообщение для запуска.")

async def cdp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in supervisors:
        supervisor = supervisors[user_id]
        snapshot = await supervisor.browser_snapshot(full=False)
        if snapshot:
            ref_count = len(snapshot.get('ref_elements', []))
            pending_dialogs = len(snapshot.get('pending_dialogs', []))
            recent_dialogs = len(snapshot.get('recent_dialogs', []))
            frames = len(snapshot.get('connected_tabs', {}))
            await update.message.reply_text(
                f"✅ **Браузер активен**\n\n"
                f"🆔 Ref ID элементов: {ref_count}\n"
                f"💬 Ожидающих диалогов: {pending_dialogs}\n"
                f"📋 Недавних диалогов: {recent_dialogs}\n"
                f"📦 Фреймов: {frames}\n"
                f"📊 Статус: Готов"
            )
        else:
            await update.message.reply_text("❌ Нет данных")
    else:
        await update.message.reply_text("❌ Браузер не запущен")

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id in supervisors:
        supervisor = supervisors[user_id]
        
        for msg_id, future in supervisor._pending_requests.items():
            if not future.done():
                future.set_exception(asyncio.CancelledError("Отменено пользователем"))
        
        supervisor._pending_requests.clear()
        
        if supervisor.pending_dialogs:
            try:
                await supervisor._send("Page.handleJavaScriptDialog", {"accept": False})
                supervisor.pending_dialogs.clear()
                await update.message.reply_text("✅ Диалог закрыт")
            except:
                pass
        
        await update.message.reply_text("✅ Операция отменена! Бот снова готов к работе.")
    else:
        await update.message.reply_text("❌ Браузер не запущен")

async def restart_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await update.message.reply_text("🔄 Перезапускаю браузер...")
    
    if user_id in supervisors:
        await supervisors[user_id].stop()
        del supervisors[user_id]
    
    subprocess.run(["pkill", "-f", "google-chrome"], capture_output=True)
    time.sleep(2)
    
    start_chrome()
    
    ws_url = get_page_ws_url()
    if not ws_url:
        ws_url = create_page()
    
    if ws_url:
        supervisor = CDPSupervisor(user_id, ws_url)
        await supervisor.start()
        supervisors[user_id] = supervisor
        await update.message.reply_text("🔄 Браузер перезапущен! ✅")
    else:
        await update.message.reply_text("❌ Не удалось перезапустить браузер")

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
        f"📋 Текущая политика диалогов: **{CURRENT_DIALOG_POLICY}**\n"
        f"⏰ Таймаут диалогов: {DIALOG_TIMEOUT_SECONDS}с\n\n"
        "Доступные политики:\n"
        "• must_respond - ждать ответа агента\n"
        "• auto_dismiss - автоматически закрывать\n"
        "• auto_accept - автоматически принимать\n\n"
        "Изменить: 'Установи политику диалогов auto_dismiss'"
    )

# ---------- Обработчик сообщений ----------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    user_id = update.message.from_user.id
    prompt = update.message.text
    
    file_logger.log(f"Сообщение от {user_id}: {prompt[:100]}...")
    
    await update.message.chat.send_action(action="typing")
    
    try:
        status_msg = await update.message.reply_text("⏳ Обрабатываю запрос...")
        
        supervisor = await get_supervisor(user_id)
        if not supervisor:
            await status_msg.edit_text("❌ Не удалось подключиться к браузеру")
            return
        
        await status_msg.edit_text("🌐 Подключаюсь к браузеру...")
        
        if not await supervisor.wait_for_ready(timeout=30):
            await status_msg.edit_text("❌ Браузер не готов (таймаут)")
            return
        
        await status_msg.edit_text("📄 Получаю состояние страницы...")
        
        page_desc = await supervisor.get_description()
        
        if AGNES_API_KEY:
            await status_msg.edit_text("🧠 Спрашиваю AI...")
            
            response = await ask_agnes(prompt, page_desc)
            if "error" not in response:
                await status_msg.edit_text("⚡ Выполняю действие...")
                
                try:
                    result = await execute_action(supervisor, response)
                    
                    if result == "screenshot":
                        img_data = await supervisor.screenshot()
                        if img_data:
                            await status_msg.delete()
                            with open("screenshot.png", "wb") as f:
                                f.write(img_data)
                            with open("screenshot.png", "rb") as photo:
                                await update.message.reply_photo(
                                    photo=photo,
                                    caption="📸 Скриншот страницы"
                                )
                        else:
                            await status_msg.edit_text("❌ Не удалось сделать скриншот")
                    else:
                        await status_msg.edit_text(f"✅ {result}")
                    
                except asyncio.CancelledError:
                    await status_msg.edit_text("⏹️ Операция отменена")
                    return
                except asyncio.TimeoutError:
                    await status_msg.edit_text("⏰ Операция заняла слишком много времени. Используй /restart")
                    return
                
                return
        
        await status_msg.edit_text("❌ Не понял команду. Попробуйте переформулировать.")
            
    except asyncio.CancelledError:
        await update.message.reply_text("⏹️ Операция отменена")
    except asyncio.TimeoutError:
        await update.message.reply_text("⏰ Операция заняла слишком много времени. Используй /restart")
    except Exception as e:
        file_logger.log(f"❌ Ошибка: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ---------- Main ----------

def timeout_handler(signum, frame):
    file_logger.log("⚠️ Таймаут всей программы, перезапуск...")
    sys.exit(1)

def main():
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(600)
    
    print("🚀 Запуск бота с полной маскировкой Pydoll...")
    file_logger.log("🚀 Запуск бота с полной маскировкой Pydoll...")
    
    start_chrome()
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("cdp", cdp))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("restart", restart_browser))
    app.add_handler(CommandHandler("reset", restart_browser))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("dialog_policy", dialog_policy_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен с Pydoll маскировкой!")
    file_logger.log("🚀 Бот запущен с Pydoll маскировкой!")
    
    try:
        app.run_polling()
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
        file_logger.log("🛑 Бот остановлен пользователем")
        sys.exit(0)

if __name__ == "__main__":
    main()