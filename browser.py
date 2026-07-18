import os
import json
import base64
import asyncio
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from mask import Mask
from cookies import get_cookies_for_url

# ===== ЦВЕТА ДЛЯ КОНСОЛИ =====
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'

# ===== ЛОГГЕР =====
class CDPLogger:
    def __init__(self, max_entries: int = 500):
        self.max_entries = max_entries
        self.log_file = "cdp_logs.json"
        self.entries = []
        self._load()
    
    def _load(self):
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, "r", encoding="utf-8") as f:
                    self.entries = json.load(f)
                    print(f"📂 Загружено {len(self.entries)} CDP записей")
        except:
            self.entries = []
    
    def add(self, method: str, params: Dict, response: Dict, duration: float):
        self.entries.append({
            "timestamp": datetime.now().isoformat(),
            "method": method,
            "params": params,
            "response": response,
            "duration": duration,
            "success": "error" not in response
        })
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]
        self._save()
    
    def _save(self):
        try:
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(self.entries, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def get_last(self, count: int = 20) -> List[Dict]:
        return self.entries[-count:] if self.entries else []

# ===== ОСНОВНОЙ КЛАСС — КАК В BROWSER-HARNESS =====
class ChromiumBrowser:
    def __init__(self, port: int = 9222):
        self.port = port
        self.process = None
        self.websocket = None
        self.ws_url = None
        self.page_id = None
        self.viewport_width = 1280
        self.viewport_height = 720
        self.chrome_path = self._find_chrome()
        self._msg_id = 0
        self.mask = Mask()
        self._keep_alive_task = None
        self._cookies_set = False
        self.logger = CDPLogger(max_entries=500)
        self._responses = {}  # Для хранения ответов на команды
        
    def _find_chrome(self) -> str:
        import shutil
        possible_names = ["chromium", "chromium-browser", "chrome", "google-chrome", "google-chrome-stable"]
        possible_paths = [
            "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/chrome",
            "/usr/bin/google-chrome", "/snap/bin/chromium", "/snap/bin/chrome",
            "/usr/local/bin/chromium", "/usr/local/bin/chrome",
            "/opt/google/chrome/chrome", "/opt/chromium/chrome",
            "/usr/lib/chromium-browser/chromium-browser",
            "/usr/lib/chromium/chromium", "/app/chromium/chrome",
            "/usr/lib/google-chrome/chrome", "/usr/lib64/google-chrome/chrome"
        ]
        
        for name in possible_names:
            path = shutil.which(name)
            if path:
                print(f"{Colors.GREEN}✅ Найден Chrome: {path}{Colors.RESET}")
                return path
        
        for path in possible_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                print(f"{Colors.GREEN}✅ Найден Chrome: {path}{Colors.RESET}")
                return path
        
        raise Exception("Chromium/Chrome не найден!")
    
    def launch(self, headless: bool = True):
        cmd = Mask.get_launch_args(self.chrome_path, self.port)
        print(f"{Colors.CYAN}🚀 Запуск браузера{Colors.RESET}")
        
        import subprocess
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(3)
        
        if self.process.poll() is not None:
            raise Exception(f"Браузер упал (код: {self.process.returncode})")
        print(f"{Colors.GREEN}✅ Браузер запущен{Colors.RESET}")
    
    async def get_ws_url(self) -> str:
        import httpx
        async with httpx.AsyncClient() as client:
            for attempt in range(5):
                try:
                    resp = await client.get(f"http://localhost:{self.port}/json/list")
                    pages = resp.json()
                    if not pages:
                        raise Exception("Нет вкладок")
                    self.page_id = pages[0]["id"]
                    return pages[0]["webSocketDebuggerUrl"]
                except:
                    await asyncio.sleep(1)
            raise Exception("Не удалось подключиться")
    
    async def connect(self):
        import websockets
        if not self.ws_url:
            self.ws_url = await self.get_ws_url()
        
        self.websocket = await websockets.connect(
            self.ws_url,
            max_size=10 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=60
        )
        print(f"{Colors.GREEN}🔗 WebSocket подключен{Colors.RESET}")
        
        await self.send_command("Page.enable")
        await self.send_command("Runtime.enable")
        await self.send_command("Network.enable")
        
        # Куки
        await self.set_all_cookies()
        
        # Маскировка
        print(f"{Colors.CYAN}🕵️ Применяю JS-маскировку...{Colors.RESET}")
        js_mask = Mask.get_js_mask()
        await self.send_command("Page.addScriptToEvaluateOnNewDocument", {"source": js_mask})
        print(f"{Colors.GREEN}✅ JS-маскировка применена{Colors.RESET}")
    
    async def set_cookies_for_url(self, url: str):
        cookies = get_cookies_for_url(url)
        if not cookies:
            return
        
        cdp_cookies = []
        for cookie in cookies:
            cdp_cookie = {
                "name": cookie.get("name"),
                "value": cookie.get("value"),
                "domain": cookie.get("domain"),
                "path": cookie.get("path", "/"),
                "secure": cookie.get("secure", False),
                "httpOnly": cookie.get("httpOnly", False),
                "sameSite": cookie.get("sameSite", "unspecified")
            }
            if not cookie.get("session", True):
                cdp_cookie["expires"] = cookie.get("expirationDate", 0)
            cdp_cookies.append(cdp_cookie)
        
        try:
            await self.send_command("Network.setCookies", {"cookies": cdp_cookies})
            print(f"{Colors.GREEN}🍪 Установлено {len(cdp_cookies)} кук{Colors.RESET}")
            self._cookies_set = True
        except Exception as e:
            print(f"{Colors.RED}⚠️ Ошибка установки кук: {e}{Colors.RESET}")
    
    async def set_all_cookies(self):
        from cookies import SITE_COOKIES
        total = 0
        for domain, cookies in SITE_COOKIES.items():
            if cookies:
                cdp_cookies = []
                for cookie in cookies:
                    cdp_cookie = {
                        "name": cookie.get("name"),
                        "value": cookie.get("value"),
                        "domain": cookie.get("domain"),
                        "path": cookie.get("path", "/"),
                        "secure": cookie.get("secure", False),
                        "httpOnly": cookie.get("httpOnly", False),
                        "sameSite": cookie.get("sameSite", "unspecified")
                    }
                    if not cookie.get("session", True):
                        cdp_cookie["expires"] = cookie.get("expirationDate", 0)
                    cdp_cookies.append(cdp_cookie)
                
                if cdp_cookies:
                    try:
                        await self.send_command("Network.setCookies", {"cookies": cdp_cookies})
                        total += len(cdp_cookies)
                        print(f"{Colors.GREEN}🍪 Установлено {len(cdp_cookies)} кук для {domain}{Colors.RESET}")
                    except:
                        pass
        
        self._cookies_set = True
        print(f"{Colors.GREEN}🍪 Всего установлено {total} кук{Colors.RESET}")
    
    # ===== ОСНОВНОЙ МЕТОД — КАК В BROWSER-HARNESS =====
    async def send_command(self, method: str, params: Dict[str, Any] = None) -> Dict:
        """Отправка CDP-команды и получение ответа"""
        try:
            if not self.websocket:
                await self.connect()
            
            self._msg_id += 1
            msg = {"id": self._msg_id, "method": method, "params": params or {}}
            
            print(f"{Colors.BLUE}📤 {method}{Colors.RESET}")
            await self.websocket.send(json.dumps(msg))
            
            while True:
                response = await self.websocket.recv()
                data = json.loads(response)
                
                # События игнорируем
                if "method" in data:
                    continue
                
                if "id" in data and data["id"] == self._msg_id:
                    if "error" in data:
                        raise Exception(f"CDP Error: {data['error']}")
                    
                    # Логируем ответ
                    try:
                        log_entry = {
                            "timestamp": datetime.now().isoformat(),
                            "method": method,
                            "params": params,
                            "response": data
                        }
                        with open("cdp_responses.log", "a", encoding="utf-8") as f:
                            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                    except:
                        pass
                    
                    return data
                
        except Exception as e:
            print(f"{Colors.RED}❌ {method} failed: {e}{Colors.RESET}")
            raise
    
    # ===== JS EVALUATION — КАК В BROWSER-HARNESS =====
    async def evaluate(self, expression: str, release: bool = True) -> Any:
        """Выполнение JavaScript — как в browser-harness"""
        try:
            result = await self.send_command("Runtime.evaluate", {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
                "allowUnsafeEvalBlockedByCSP": True,
                "userGesture": True,
                "includeCommandLineAPI": False,
            })
            
            # Проверка на ошибки
            if "exceptionDetails" in result:
                error_text = result.get("exceptionDetails", {}).get("text", "Unknown error")
                print(f"{Colors.RED}❌ JS Error: {error_text}{Colors.RESET}")
                return None
            
            # Получаем значение
            value = result.get("result", {}).get("result", {}).get("value")
            
            # Если значение None — это нормально (просто нет данных)
            if value is None:
                print(f"{Colors.YELLOW}⚠️ Результат: None (нет данных){Colors.RESET}")
            else:
                print(f"{Colors.GREEN}✅ Результат: {str(value)[:200]}{Colors.RESET}")
            
            return value
            
        except Exception as e:
            print(f"{Colors.RED}❌ Ошибка evaluate: {e}{Colors.RESET}")
            return None
    
    # ===== НАВИГАЦИЯ — КАК В BROWSER-HARNESS =====
    async def navigate(self, url: str) -> Dict:
        """Переход по URL — как в browser-harness"""
        print(f"{Colors.CYAN}🌐 Переход на {url}{Colors.RESET}")
        
        if not self._cookies_set:
            await self.set_cookies_for_url(url)
        
        # Отправляем навигацию
        result = await self.send_command("Page.navigate", {"url": url})
        
        # Ждём загрузки (как в browser-harness)
        for attempt in range(30):
            try:
                ready_state = await self.evaluate("document.readyState")
                if ready_state == "complete":
                    print(f"{Colors.GREEN}✅ Страница загружена (попытка {attempt+1}){Colors.RESET}")
                    break
            except:
                pass
            await asyncio.sleep(0.5)
        
        # Ждём контент для body
        for attempt in range(20):
            try:
                body_text = await self.evaluate("document.body?.innerText?.length || 0")
                if body_text and body_text > 10:
                    print(f"{Colors.GREEN}✅ Контент загружен ({body_text} символов){Colors.RESET}")
                    break
            except:
                pass
            await asyncio.sleep(0.5)
        
        # Особое ожидание для X.com
        if "x.com" in url or "twitter.com" in url:
            print(f"{Colors.CYAN}🐦 Дополнительное ожидание для X.com...{Colors.RESET}")
            await asyncio.sleep(3)
            await self.wait_for_element("article[data-testid='tweet']", timeout=10)
        
        return result
    
    # ===== ОЖИДАНИЕ ЭЛЕМЕНТА — КАК В BROWSER-HARNESS =====
    async def wait_for_element(self, selector: str, timeout: int = 15) -> bool:
        """Ожидание элемента — как в browser-harness"""
        print(f"{Colors.YELLOW}⏳ Ожидание: {selector}{Colors.RESET}")
        
        # Для body — ждём контент
        if selector == "body":
            check = f"document.body && document.body.innerText.length > 10"
        else:
            check = f"document.querySelector({json.dumps(selector)}) && document.querySelector({json.dumps(selector)}).offsetParent !== null"
        
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                result = await self.evaluate(f"!!({check})")
                if result:
                    print(f"{Colors.GREEN}✅ Элемент найден: {selector}{Colors.RESET}")
                    return True
            except:
                pass
            await asyncio.sleep(0.3)
        
        print(f"{Colors.RED}⚠️ Таймаут: {selector} не найден{Colors.RESET}")
        return False
    
    # ===== ОСТАЛЬНЫЕ МЕТОДЫ =====
    
    async def wait_for_load(self, timeout: float = 15.0) -> bool:
        """Ожидание полной загрузки страницы"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                ready = await self.evaluate("document.readyState")
                if ready == "complete":
                    return True
            except:
                pass
            await asyncio.sleep(0.3)
        return False
    
    async def screenshot(self, format: str = "png") -> bytes:
        """Скриншот"""
        print(f"{Colors.CYAN}📸 Делаю скриншот...{Colors.RESET}")
        await self.send_command("Emulation.setDeviceMetricsOverride", {
            "width": self.viewport_width,
            "height": self.viewport_height,
            "deviceScaleFactor": 1,
            "mobile": False,
            "scale": 1,
            "screenWidth": self.viewport_width,
            "screenHeight": self.viewport_height,
        })
        result = await self.send_command("Page.captureScreenshot", {
            "format": format,
            "captureBeyondViewport": False
        })
        if "result" in result and "data" in result["result"]:
            return base64.b64decode(result["result"]["data"])
        elif "data" in result:
            return base64.b64decode(result["data"])
        raise Exception("Неизвестный ответ CDP")
    
    async def click_human(self, selector: str):
        print(f"{Colors.CYAN}🖱️ Клик по {selector}{Colors.RESET}")
        js_code = Mask.get_human_click_js(selector)
        result = await self.evaluate(js_code)
        if not result:
            raise Exception(f"Не удалось кликнуть по {selector}")
        await asyncio.sleep(0.3)
    
    async def type_human(self, selector: str, text: str):
        print(f"{Colors.CYAN}⌨️ Ввод: {text}{Colors.RESET}")
        js_code = Mask.get_human_type_js(selector, text)
        result = await self.evaluate(js_code)
        if not result:
            raise Exception(f"Не удалось ввести текст в {selector}")
        await asyncio.sleep(0.3)
    
    async def scroll_human(self, distance: int):
        print(f"{Colors.CYAN}📜 Скролл: {distance}px{Colors.RESET}")
        js_code = Mask.get_human_scroll_js(distance)
        result = await self.evaluate(js_code)
        if not result:
            raise Exception("Не удалось выполнить скролл")
        await asyncio.sleep(0.3)
    
    async def disconnect(self):
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            print(f"{Colors.CYAN}🔌 WebSocket отключен{Colors.RESET}")
    
    def close(self):
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None
            print(f"{Colors.CYAN}🛑 Браузер закрыт{Colors.RESET}")
    
    def get_logs(self, count: int = 20) -> List[Dict]:
        return self.logger.get_last(count)