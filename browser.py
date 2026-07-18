import subprocess
import time
import json
import asyncio
import httpx
import websockets
import base64
import shutil
import os
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
    BOLD = '\033[1m'

# ===== ЛОГГЕР С РОТАЦИЕЙ =====
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
                    print(f"📂 Загружено {len(self.entries)} CDP записей из {self.log_file}")
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
        except Exception as e:
            print(f"⚠️ Ошибка сохранения CDP лога: {e}")
    
    def get_last(self, count: int = 20) -> List[Dict]:
        return self.entries[-count:] if self.entries else []
    
    def get_by_method(self, method: str) -> List[Dict]:
        return [e for e in self.entries if e.get("method") == method]
    
    def clear(self):
        self.entries = []
        self._save()
        print("🧹 CDP лог очищен")

# ===== ОСНОВНОЙ КЛАСС =====
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
        
    def _find_chrome(self) -> str:
        possible_names = [
            "chromium", "chromium-browser", "chrome", "google-chrome",
            "google-chrome-stable", "chrome-browser"
        ]
        possible_paths = [
            "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/chrome",
            "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
            "/snap/bin/chromium", "/snap/bin/chrome",
            "/usr/local/bin/chromium", "/usr/local/bin/chrome",
            "/opt/google/chrome/chrome", "/opt/chromium/chrome",
            "/usr/lib/chromium-browser/chromium-browser",
            "/usr/lib/chromium/chromium", "/app/chromium/chrome",
            "/usr/lib/google-chrome/chrome", "/usr/lib64/google-chrome/chrome"
        ]
        
        for name in possible_names:
            path = shutil.which(name)
            if path:
                print(f"{Colors.GREEN}✅ Найден Chrome (which): {path}{Colors.RESET}")
                return path
        
        for path in possible_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                print(f"{Colors.GREEN}✅ Найден Chrome (путь): {path}{Colors.RESET}")
                return path
        
        try:
            result = subprocess.run(
                ["find", "/", "-name", "chromium", "-type", "f", "-executable"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().split('\n'):
                if line and os.access(line, os.X_OK):
                    print(f"{Colors.GREEN}✅ Найден Chrome (find): {line}{Colors.RESET}")
                    return line
        except:
            pass
        
        raise Exception("Chromium/Chrome не найден! Установи через: apt-get install chromium")
    
    def launch(self, headless: bool = True):
        cmd = Mask.get_launch_args(self.chrome_path, self.port)
        
        print(f"{Colors.CYAN}🚀 Запуск браузера с маскировкой: {self.chrome_path}{Colors.RESET}")
        print(f"{Colors.YELLOW}📋 Команда: {' '.join(cmd)}{Colors.RESET}")
        
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(3)
        
        if self.process.poll() is not None:
            raise Exception(f"Браузер упал при запуске (код: {self.process.returncode})")
        print(f"{Colors.GREEN}✅ Браузер запущен с маскировкой{Colors.RESET}")
        
    async def get_ws_url(self) -> str:
        async with httpx.AsyncClient() as client:
            for attempt in range(5):
                try:
                    resp = await client.get(f"http://localhost:{self.port}/json/list")
                    pages = resp.json()
                    if not pages:
                        raise Exception("Нет открытых вкладок")
                    self.page_id = pages[0]["id"]
                    ws_url = pages[0]["webSocketDebuggerUrl"]
                    print(f"{Colors.CYAN}📄 Найдена страница: {self.page_id}{Colors.RESET}")
                    return ws_url
                except Exception as e:
                    if attempt < 4:
                        print(f"{Colors.YELLOW}⏳ Ожидание браузера (попытка {attempt+1}/5)...{Colors.RESET}")
                        await asyncio.sleep(1)
                    else:
                        raise Exception(f"Не удалось подключиться к браузеру: {e}")
    
    async def _keep_alive(self):
        while True:
            try:
                if self.websocket is not None:
                    await asyncio.sleep(15)
                    await self.websocket.ping()
                    print(f"{Colors.MAGENTA}💓 WebSocket ping отправлен{Colors.RESET}")
                else:
                    print(f"{Colors.YELLOW}⏳ WebSocket не инициализирован, keep-alive ждёт...{Colors.RESET}")
                    await asyncio.sleep(2)
            except websockets.exceptions.ConnectionClosed:
                print(f"{Colors.RED}⚠️ WebSocket закрыт, переподключаюсь...{Colors.RESET}")
                self.websocket = None
                try:
                    await self.connect()
                except Exception as e:
                    print(f"{Colors.RED}❌ Ошибка переподключения: {e}{Colors.RESET}")
                    await asyncio.sleep(5)
            except Exception as e:
                print(f"{Colors.RED}⚠️ Keep-alive ошибка: {e}{Colors.RESET}")
                await asyncio.sleep(5)
    
    async def set_cookies_for_url(self, url: str):
        cookies = get_cookies_for_url(url)
        if not cookies:
            print(f"{Colors.YELLOW}🍪 Нет кук для {url}{Colors.RESET}")
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
            result = await self.send_command("Network.setCookies", {"cookies": cdp_cookies})
            print(f"{Colors.GREEN}🍪 Установлено {len(cdp_cookies)} кук для {url}{Colors.RESET}")
            self._cookies_set = True
            return result
        except Exception as e:
            print(f"{Colors.RED}⚠️ Ошибка установки кук: {e}{Colors.RESET}")
            return None
    
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
                    except Exception as e:
                        print(f"{Colors.RED}⚠️ Ошибка установки кук для {domain}: {e}{Colors.RESET}")
        
        self._cookies_set = True
        print(f"{Colors.GREEN}🍪 Всего установлено {total} кук{Colors.RESET}")
        return total
    
    async def connect(self):
        if not self.ws_url:
            self.ws_url = await self.get_ws_url()
        
        self.websocket = await websockets.connect(
            self.ws_url,
            max_size=10 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=60
        )
        print(f"{Colors.GREEN}🔗 WebSocket подключен (макс. размер: 10 МБ, ping_timeout: 60 сек){Colors.RESET}")
        
        if self._keep_alive_task is None or self._keep_alive_task.done():
            self._keep_alive_task = asyncio.create_task(self._keep_alive())
        
        await self.send_command("Page.enable")
        await self.send_command("Runtime.enable")
        await self.send_command("Network.enable")
        
        await self.set_all_cookies()
        
        print(f"{Colors.CYAN}🕵️ Применяю JS-маскировку...{Colors.RESET}")
        js_mask = Mask.get_js_mask()
        await self.send_command("Page.addScriptToEvaluateOnNewDocument", {"source": js_mask})
        print(f"{Colors.GREEN}✅ JS-маскировка применена{Colors.RESET}")
        
    async def release_object(self, object_id: str):
        try:
            await self.send_command("Runtime.releaseObject", {"objectId": object_id})
        except:
            pass
    
    async def evaluate(self, expression: str, release: bool = True) -> Any:
        """
        Выполняет JavaScript на странице через CDP Runtime.evaluate.
        """
        start_time = datetime.now()
        
        # ===== ЛОГИРУЕМ ЗАПРОС =====
        print(f"{Colors.BLUE}📤 [{start_time.strftime('%H:%M:%S')}] Runtime.evaluate{Colors.RESET}")
        print(f"{Colors.CYAN}   📋 {expression[:200]}{Colors.RESET}")
        
        params = {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
            "allowUnsafeEvalBlockedByCSP": True,
            "userGesture": True,
            "includeCommandLineAPI": False,
        }
        
        result = await self.send_command("Runtime.evaluate", params)
        
        duration = (datetime.now() - start_time).total_seconds()
        
        if "exceptionDetails" in result:
            print(f"{Colors.RED}❌ JS Error: {result['exceptionDetails']}{Colors.RESET}")
            raise Exception(f"JS Error: {result['exceptionDetails']}")
        
        value = result.get("result", {}).get("result", {}).get("value")
        
        # ===== ЛОГИРУЕМ РЕЗУЛЬТАТ =====
        print(f"{Colors.GREEN}   ✅ Runtime.evaluate ({duration:.2f}s){Colors.RESET}")
        if value is not None:
            print(f"{Colors.CYAN}   📊 Результат: {str(value)[:200]}{Colors.RESET}")
        
        # ===== ЗАПИСЫВАЕМ В ОТДЕЛЬНЫЙ ФАЙЛ =====
        try:
            # Создаём папку если нет
            os.makedirs("logs", exist_ok=True)
            
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "type": "evaluate",
                "expression": expression,
                "params": params,
                "result": result,
                "value": value,
                "duration": duration,
                "success": True
            }
            
            # В отдельный файл для eval
            with open("logs/evaluate.log", "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
            # Также в общий лог
            with open("cdp_responses.log", "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "timestamp": datetime.now().isoformat(),
                    "method": "Runtime.evaluate (user)",
                    "expression": expression[:500],
                    "result": value,
                    "duration": duration
                }, ensure_ascii=False) + "\n")
                
        except Exception as e:
            print(f"{Colors.RED}⚠️ Ошибка записи eval лога: {e}{Colors.RESET}")
        
        if release and "result" in result and "objectId" in result["result"]:
            object_id = result["result"]["objectId"]
            await self.release_object(object_id)
        
        return value
    
    async def evaluate_fast(self, expression: str) -> None:
        await self.send_command("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": False,
            "awaitPromise": True,
            "userGesture": True,
        })
    
    async def send_command(self, method: str, params: Dict[str, Any] = None) -> Dict:
        start_time = datetime.now()
        
        try:
            if not self.websocket:
                await self.connect()
            
            self._msg_id += 1
            msg = {"id": self._msg_id, "method": method, "params": params or {}}
            
            timestamp = start_time.strftime("%H:%M:%S")
            print(f"{Colors.BLUE}📤 [{timestamp}] {method}{Colors.RESET}")
            
            if params and len(str(params)) < 500:
                print(f"{Colors.CYAN}   📋 {json.dumps(params, ensure_ascii=False)[:200]}{Colors.RESET}")
            
            await self.websocket.send(json.dumps(msg))
            
            while True:
                response = await self.websocket.recv()
                data = json.loads(response)
                if "id" in data:
                    duration = (datetime.now() - start_time).total_seconds()
                    
                    is_error = "error" in data
                    status_emoji = "❌" if is_error else "✅"
                    status_color = Colors.RED if is_error else Colors.GREEN
                    
                    print(f"{status_color}   {status_emoji} {method} ({duration:.2f}s){Colors.RESET}")
                    
                    if is_error:
                        print(f"{Colors.RED}   ❌ {data['error']}{Colors.RESET}")
                    
                    self.logger.add(method, params, data, duration)
                    
                    try:
                        log_entry = {
                            "timestamp": datetime.now().isoformat(),
                            "method": method,
                            "params": params,
                            "response": data,
                            "duration": duration
                        }
                        with open("cdp_responses.log", "a", encoding="utf-8") as f:
                            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                    except Exception as e:
                        print(f"{Colors.RED}⚠️ Ошибка записи CDP лога: {e}{Colors.RESET}")
                    
                    if is_error:
                        with open("cdp_errors.log", "a", encoding="utf-8") as f:
                            f.write(json.dumps({
                                "timestamp": datetime.now().isoformat(),
                                "method": method,
                                "params": params,
                                "error": data["error"]
                            }, ensure_ascii=False) + "\n")
                        print(f"{Colors.RED}❌ CDP Error в {method}: {data['error']}{Colors.RESET}")
                        raise Exception(f"CDP Error: {data['error']}")
                    
                    important_methods = ["Page.navigate", "Page.captureScreenshot", "Runtime.evaluate"]
                    if method in important_methods:
                        try:
                            os.makedirs("logs", exist_ok=True)
                            with open(f"logs/{method}.log", "a", encoding="utf-8") as f:
                                f.write(json.dumps({
                                    "timestamp": datetime.now().isoformat(),
                                    "params": params,
                                    "response": data
                                }, ensure_ascii=False) + "\n")
                        except:
                            pass
                    
                    return data
                print(f"{Colors.YELLOW}📡 Событие: {data.get('method')}{Colors.RESET}")
                
        except (websockets.exceptions.ConnectionClosed, websockets.exceptions.WebSocketException) as e:
            print(f"{Colors.RED}⚠️ WebSocket упал: {e}. Переподключаюсь...{Colors.RESET}")
            self.websocket = None
            await self.connect()
            return await self.send_command(method, params)
        except Exception as e:
            print(f"{Colors.RED}❌ {method} failed: {e}{Colors.RESET}")
            raise
    
    def get_logs(self, count: int = 20) -> List[Dict]:
        return self.logger.get_last(count)
    
    def get_logs_by_method(self, method: str) -> List[Dict]:
        return self.logger.get_by_method(method)
    
    def clear_logs(self):
        self.logger.clear()
        if os.path.exists("cdp_responses.log"):
            os.remove("cdp_responses.log")
        print("🧹 Все CDP логи очищены")
    
    async def set_viewport(self, width: int = 1280, height: int = 720):
        self.viewport_width = width
        self.viewport_height = height
        params = {
            "width": width, "height": height, "deviceScaleFactor": 1,
            "mobile": False, "scale": 1, "screenWidth": width,
            "screenHeight": height, "positionX": 0, "positionY": 0
        }
        await self.send_command("Emulation.setDeviceMetricsOverride", params)
        print(f"{Colors.CYAN}📐 Установлен размер окна: {width}x{height}{Colors.RESET}")
    
    async def wait_for_element(self, selector: str, timeout: int = 15, interval: float = 0.3):
        print(f"{Colors.YELLOW}⏳ Ожидание элемента: {selector}{Colors.RESET}")
        
        js_wait = f"""
        (function() {{
            return new Promise((resolve, reject) => {{
                const start = Date.now();
                const check = () => {{
                    const el = document.querySelector('{selector}');
                    if (el && el.offsetParent !== null) {{
                        resolve(true);
                    }} else if (Date.now() - start > {timeout * 1000}) {{
                        resolve(false);
                    }} else {{
                        setTimeout(check, {int(interval * 1000)});
                    }};
                }};
                check();
            }});
        }})()
        """
        
        try:
            result = await self.evaluate(js_wait, release=True)
            if result:
                print(f"{Colors.GREEN}✅ Элемент найден: {selector}{Colors.RESET}")
                return True
            else:
                print(f"{Colors.RED}⚠️ Таймаут: {selector} не найден за {timeout} сек{Colors.RESET}")
                return False
        except Exception as e:
            print(f"{Colors.RED}⚠️ Ошибка ожидания {selector}: {e}{Colors.RESET}")
            return False
    
    async def navigate(self, url: str) -> Dict:
        print(f"{Colors.CYAN}🌐 Переход на {url}{Colors.RESET}")
        
        if not self._cookies_set:
            await self.set_cookies_for_url(url)
        
        await self.send_command("Page.enable")
        result = await self.send_command("Page.navigate", {"url": url})
        
        for attempt in range(30):
            await asyncio.sleep(0.5)
            try:
                ready_state = await self.evaluate("document.readyState")
                if ready_state == "complete":
                    print(f"{Colors.GREEN}✅ Страница загружена (попытка {attempt+1}){Colors.RESET}")
                    break
            except Exception as e:
                print(f"{Colors.YELLOW}⏳ Ожидание загрузки... ({attempt+1}/30){Colors.RESET}")
        
        if "x.com" in url or "twitter.com" in url:
            print(f"{Colors.CYAN}🐦 Дополнительное ожидание для X.com (3 сек)...{Colors.RESET}")
            await asyncio.sleep(3)
            await self.wait_for_element("article[data-testid='tweet']", timeout=10)
        
        await asyncio.sleep(1)
        return result
    
    async def extract(self, model_name: str, timeout: int = 10) -> Dict:
        from agent import X_EXTRACTION
        if not X_EXTRACTION:
            print(f"{Colors.RED}⚠️ x-com-extraction.json не загружен{Colors.RESET}")
            return {}
        
        models = X_EXTRACTION.get("models", {})
        model = models.get(model_name)
        if not model:
            print(f"{Colors.RED}⚠️ Модель '{model_name}' не найдена{Colors.RESET}")
            return {}
        
        container_selector = model.get("container")
        if container_selector:
            await self.wait_for_element(container_selector, timeout=timeout)
        
        fields = model.get("fields", {})
        result = {}
        
        for field_name, field_config in fields.items():
            selector = field_config.get("selector")
            transform = field_config.get("transform")
            if not selector:
                continue
            
            js = f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return '';
                if (el.tagName === 'IMG') return el.src || '';
                return el.innerText?.trim() || el.value || el.placeholder || '';
            }})()
            """
            
            try:
                value = await self.evaluate(js, release=True)
                if transform == "int":
                    if isinstance(value, str):
                        value = value.replace(',', '').replace('.', '').strip()
                    value = int(value) if value else 0
                elif transform == "exists":
                    value = bool(value)
                elif transform == "list":
                    value = [value] if value else []
                elif transform == "extract_tweet_id":
                    if value and "/status/" in value:
                        value = value.split("/status/")[-1].split("?")[0]
                result[field_name] = value
            except Exception as e:
                print(f"{Colors.RED}⚠️ Ошибка извлечения {field_name}: {e}{Colors.RESET}")
                result[field_name] = None
        
        return result
    
    async def extract_all(self, model_name: str, timeout: int = 10, limit: int = 20) -> List[Dict]:
        from agent import X_EXTRACTION
        if not X_EXTRACTION:
            return []
        
        models = X_EXTRACTION.get("models", {})
        model = models.get(model_name)
        if not model:
            return []
        
        container_selector = model.get("container")
        if not container_selector:
            return [await self.extract(model_name, timeout)]
        
        await self.wait_for_element(container_selector, timeout=timeout)
        
        fields = model.get("fields", {})
        results = []
        
        for i in range(limit):
            item_result = {}
            has_value = False
            
            for field_name, field_config in fields.items():
                selector = field_config.get("selector")
                transform = field_config.get("transform")
                if not selector:
                    continue
                
                js = f"""
                (function() {{
                    const items = document.querySelectorAll('{container_selector}');
                    if (items.length <= {i}) return '';
                    const el = items[{i}].querySelector('{selector}');
                    if (!el) return '';
                    if (el.tagName === 'IMG') return el.src || '';
                    return el.innerText?.trim() || el.value || el.placeholder || '';
                }})()
                """
                
                try:
                    value = await self.evaluate(js, release=True)
                    if transform == "int":
                        if isinstance(value, str):
                            value = value.replace(',', '').strip()
                        value = int(value) if value else 0
                    elif transform == "exists":
                        value = bool(value)
                    elif transform == "list":
                        value = [value] if value else []
                    item_result[field_name] = value
                    if value:
                        has_value = True
                except:
                    item_result[field_name] = None
            
            if has_value:
                results.append(item_result)
            else:
                break
        
        return results
    
    async def screenshot(self, format: str = "png") -> bytes:
        print(f"{Colors.CYAN}📸 Делаю скриншот...{Colors.RESET}")
        
        await self.set_viewport(self.viewport_width, self.viewport_height)
        result = await self.send_command(
            "Page.captureScreenshot",
            {"format": format, "captureBeyondViewport": False}
        )
        if "result" in result and "data" in result["result"]:
            return base64.b64decode(result["result"]["data"])
        elif "data" in result:
            return base64.b64decode(result["data"])
        else:
            raise Exception(f"Неизвестный ответ CDP: {result}")
    
    async def click_human(self, selector: str):
        print(f"{Colors.CYAN}🖱️ Человеческий клик по {selector}{Colors.RESET}")
        js_code = Mask.get_human_click_js(selector)
        result = await self.evaluate(js_code, release=True)
        if not result:
            raise Exception(f"Не удалось кликнуть по {selector}")
        await asyncio.sleep(0.5)
    
    async def type_human(self, selector: str, text: str):
        print(f"{Colors.CYAN}⌨️ Человеческий ввод: {text}{Colors.RESET}")
        js_code = Mask.get_human_type_js(selector, text)
        result = await self.evaluate(js_code, release=True)
        if not result:
            raise Exception(f"Не удалось ввести текст в {selector}")
        await asyncio.sleep(0.5)
    
    async def scroll_human(self, distance: int):
        print(f"{Colors.CYAN}📜 Человеческий скролл: {distance}px{Colors.RESET}")
        js_code = Mask.get_human_scroll_js(distance)
        result = await self.evaluate(js_code, release=True)
        if not result:
            raise Exception("Не удалось выполнить скролл")
        await asyncio.sleep(0.3)
    
    async def disconnect(self):
        if self._keep_alive_task and not self._keep_alive_task.done():
            self._keep_alive_task.cancel()
            try:
                await self._keep_alive_task
            except:
                pass
            self._keep_alive_task = None
        
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