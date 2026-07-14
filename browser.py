import asyncio
import json
import websockets
import requests
import base64
from typing import Optional

class BrowserManager:
    def __init__(self, host='localhost', port=9222):
        self.host = host
        self.port = port
        self.ws = None
        self.ws_url = None
        self._message_id = 0
        self._connected = False
        self._page_id = None
        self._current_url = ""  # ← Добавил
        
        self.viewport_width = 1280
        self.viewport_height = 720
        self.timeout = 60
    
    def _get_tab_ws_url(self, tab_id: Optional[str] = None) -> Optional[str]:
        try:
            resp = requests.get(f'http://{self.host}:{self.port}/json/list', timeout=5)
            if resp.status_code != 200:
                return None
            
            pages = resp.json()
            
            if not pages:
                resp = requests.get(f'http://{self.host}:{self.port}/json/new', timeout=5)
                new_page = resp.json()
                self._page_id = new_page.get('id')
                self._current_url = new_page.get('url', '')
                return new_page['webSocketDebuggerUrl']
            
            if tab_id:
                for page in pages:
                    if page.get('id') == tab_id:
                        self._page_id = page['id']
                        self._current_url = page.get('url', '')
                        return page['webSocketDebuggerUrl']
            
            first_page = pages[0]
            self._page_id = first_page.get('id')
            self._current_url = first_page.get('url', '')
            return first_page['webSocketDebuggerUrl']
            
        except Exception as e:
            print(f"❌ Ошибка подключения к Chrome: {e}")
            return None
    
    async def connect(self, tab_id: Optional[str] = None):
        if self._connected and self.ws:
            return
        
        self.ws_url = self._get_tab_ws_url(tab_id)
        if not self.ws_url:
            raise Exception("❌ Chrome не запущен или нет доступных вкладок")
        
        print(f"🔗 Подключаюсь к: {self.ws_url}")
        self.ws = await websockets.connect(
            self.ws_url,
            max_size=50 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=60
        )
        self._connected = True
        
        await self._send_command("Page.enable")
        await self._send_command("Runtime.enable")
        await self._send_command("DOM.enable")
        await self._send_command("Network.enable")
        
        await self._set_viewport()
        print("✅ Подключение к CDP установлено")
    
    async def _set_viewport(self):
        await self._send_command("Emulation.setDeviceMetricsOverride", {
            "width": self.viewport_width,
            "height": self.viewport_height,
            "deviceScaleFactor": 1,
            "mobile": False
        })
    
    async def _send_command(self, method: str, params: dict = None):
        if not self._connected:
            await self.connect()
        
        self._message_id += 1
        message = {
            "id": self._message_id,
            "method": method,
            "params": params or {}
        }
        
        await self.ws.send(json.dumps(message))
        print(f"📤 Отправлена команда: {method} (id: {self._message_id})")
        
        while True:
            try:
                response = await asyncio.wait_for(self.ws.recv(), timeout=self.timeout)
                data = json.loads(response)
                
                if data.get('id') == self._message_id:
                    if 'error' in data:
                        raise Exception(f"CDP Error: {data['error']}")
                    print(f"📥 Получен ответ на {method}")
                    return data.get('result', {})
            except asyncio.TimeoutError:
                raise Exception(f"❌ Таймаут ответа от Chrome на команду {method}")
    
    async def open_page(self, url: str):
        await self.connect()
        result = await self._send_command("Page.navigate", {"url": url})
        self._current_url = url
        await asyncio.sleep(2)
        await self._set_viewport()
        return result
    
    async def is_page_empty(self) -> bool:
        """Проверить, пустая ли страница"""
        try:
            # Проверяем URL
            if not self._current_url or self._current_url in ['about:blank', 'chrome://newtab/', '']:
                return True
            
            # Проверяем текст
            text = await self.get_page_text()
            if not text or text.strip() == "":
                return True
            
            # Проверяем заголовок
            title = await self.get_page_title()
            if not title or title.strip() == "":
                return True
            
            return False
        except:
            return True
    
    async def screenshot(self):
        await self.connect()
        
        # Проверяем, что страница не пустая
        if await self.is_page_empty():
            raise Exception("📭 Страница пустая или не загружена. Сначала откройте страницу командой /open")
        
        await self._set_viewport()
        
        result = await self._send_command("Page.captureScreenshot", {
            "format": "png",
            "captureBeyondViewport": False
        })
        
        screenshot_data = result['data']
        screenshot_data = screenshot_data.strip()
        if ',' in screenshot_data:
            screenshot_data = screenshot_data.split(',')[-1]
        screenshot_data = ''.join(screenshot_data.split())
        
        return screenshot_data
    
    async def get_page_text(self):
        await self.connect()
        
        # Проверяем, есть ли что-то на странице
        try:
            result = await self._send_command("Runtime.evaluate", {
                "expression": "document.body?.innerText || document.documentElement?.textContent || ''"
            })
            text = result['result'].get('value', '')
            
            # Проверяем, не пустой ли текст
            if not text or text.strip() == "":
                return "📭 Страница пустая или не содержит текста"
            
            return text[:10000]
        except Exception as e:
            return f"⚠️ Не удалось получить текст: {str(e)[:100]}"
    
    async def get_page_title(self):
        await self.connect()
        try:
            result = await self._send_command("Runtime.evaluate", {
                "expression": "document.title || ''"
            })
            title = result['result'].get('value', '')
            if not title or title.strip() == "":
                return "Без названия"
            return title
        except:
            return "Без названия"
    
    async def click_element(self, selector: str):
        await self.connect()
        
        # Проверяем, что страница не пустая
        if await self.is_page_empty():
            return "❌ Страница пустая. Сначала откройте страницу командой /open"
        
        find_result = await self._send_command("DOM.querySelector", {
            "selector": selector
        })
        node_id = find_result.get('nodeId')
        
        if not node_id or node_id == 0:
            return "❌ Элемент не найден"
        
        box_result = await self._send_command("DOM.getBoxModel", {
            "nodeId": node_id
        })
        
        if not box_result or 'model' not in box_result:
            return "❌ Не удалось получить координаты"
        
        content = box_result['model']['content']
        x = (content[0] + content[4]) / 2
        y = (content[1] + content[5]) / 2
        
        await self._send_command("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1
        })
        await self._send_command("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1
        })
        
        return f"✅ Кликнул по: {selector}"
    
    async def execute_script(self, script: str):
        await self.connect()
        
        # Проверяем, что страница не пустая
        if await self.is_page_empty() and script not in ['document.title', 'location.href']:
            return "⚠️ Страница пустая. Сначала откройте страницу командой /open"
        
        result = await self._send_command("Runtime.evaluate", {
            "expression": script,
            "returnByValue": True
        })
        
        value = result['result'].get('value')
        return value if value is not None else 'undefined'
    
    async def go_back(self):
        await self.connect()
        
        if await self.is_page_empty():
            return "❌ Страница пустая, некуда возвращаться"
        
        await self._send_command("Page.navigateBack")
        await asyncio.sleep(1)
    
    async def go_forward(self):
        await self.connect()
        
        if await self.is_page_empty():
            return "❌ Страница пустая, некуда идти вперёд"
        
        await self._send_command("Page.navigateForward")
        await asyncio.sleep(1)
    
    async def refresh(self):
        await self.connect()
        
        if await self.is_page_empty():
            return "❌ Страница пустая, нечего обновлять"
        
        await self._send_command("Page.reload", {"ignoreCache": True})
        await asyncio.sleep(1)
    
    async def list_tabs(self):
        try:
            resp = requests.get(f'http://{self.host}:{self.port}/json/list', timeout=5)
            pages = resp.json()
            
            if not pages:
                return "📭 Нет открытых вкладок"
            
            result = "📑 Список вкладок:\n\n"
            for i, page in enumerate(pages):
                title = page.get('title', 'Без названия')[:40]
                url = page.get('url', '')[:40]
                active = "🔵" if page.get('id') == self._page_id else "⚪"
                result += f"{active} {i+1}. {title}\n   {url}\n\n"
            return result
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def create_tab(self, url: str = ""):
        try:
            resp = requests.get(f'http://{self.host}:{self.port}/json/new', timeout=5)
            page = resp.json()
            
            await self.close()
            
            self._page_id = page.get('id')
            self._current_url = page.get('url', '')
            await self.connect(self._page_id)
            
            if url:
                await self.open_page(url)
            
            return f"✅ Создана вкладка: {page.get('title', 'Новая вкладка')}"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def close_tab(self):
        if not self._page_id:
            return "❌ Нет активной вкладки"
        
        try:
            requests.get(f'http://{self.host}:{self.port}/json/close/{self._page_id}', timeout=5)
            await self.close()
            
            await self.connect()
            return "✅ Вкладка закрыта"
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    async def close(self):
        if self.ws and self._connected:
            try:
                await self.ws.close()
            except:
                pass
            self._connected = False
            self.ws = None