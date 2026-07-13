# bot.py
import asyncio
import json
import os
import subprocess
import time
import base64
import hashlib
import websockets
import aiohttp
from datetime import datetime
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "ВАШ_ТОКЕН")
CHROME_PATH = os.getenv("CHROME_PATH", "/usr/bin/google-chrome")
CDP_PORT = 9222
SNAPSHOT_DIR = "snapshots"

os.makedirs(SNAPSHOT_DIR, exist_ok=True)

# ==================== CHROME MANAGER ====================
class ChromeManager:
    def __init__(self):
        self.process = None
        self.port = CDP_PORT
    
    def start(self):
        cmd = [
            CHROME_PATH,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox",
            "--disable-software-rasterizer",
            "--window-size=1920,1080",
            f"--remote-debugging-port={self.port}"
        ]
        
        print(f"🚀 Запускаю Chrome")
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        time.sleep(3)
        return self.port
    
    def stop(self):
        if self.process:
            self.process.terminate()
            self.process.wait()

# ==================== CDP CONTROLLER ====================
class CDPController:
    def __init__(self, port=CDP_PORT):
        self.port = port
        self.ws = None
        self.target_id = None
        self.msg_id = 0
        self._session_id = None
        
    async def connect(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://localhost:{self.port}/json/version") as resp:
                data = await resp.json()
                ws_url = data["webSocketDebuggerUrl"]
        
        self.ws = await websockets.connect(ws_url)
        return self
    
    async def send(self, method, params=None, session_id=None):
        self.msg_id += 1
        msg = {"id": self.msg_id, "method": method, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        
        await self.ws.send(json.dumps(msg))
        
        while True:
            response = json.loads(await self.ws.recv())
            if response.get("id") == self.msg_id:
                if "error" in response:
                    raise RuntimeError(f"CDP error: {response['error']}")
                return response.get("result")
    
    async def create_tab(self, url="about:blank"):
        result = await self.send("Target.createTarget", {"url": url})
        self.target_id = result["targetId"]
        return self.target_id
    
    async def attach_to_tab(self, target_id=None):
        tid = target_id or self.target_id
        result = await self.send("Target.attachToTarget", {
            "targetId": tid,
            "flatten": True
        })
        session_id = result["sessionId"]
        self._session_id = session_id
        
        # Включаем все нужные домены
        await self.send("Page.enable", session_id=session_id)
        await self.send("Runtime.enable", session_id=session_id)
        await self.send("DOM.enable", session_id=session_id)
        await self.send("Network.enable", session_id=session_id)
        await self.send("Log.enable", session_id=session_id)
        
        return session_id
    
    async def wait_for_load(self, session_id, timeout=30):
        """Ожидание загрузки страницы (включая SPA)"""
        start = time.time()
        loaded = False
        network_idle = False
        
        while time.time() - start < timeout:
            try:
                response = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=1))
                method = response.get("method")
                
                # Ждём событие загрузки
                if method == "Page.loadEventFired":
                    loaded = True
                
                # SPA: ждём, когда сеть станет бездействовать
                if method == "Network.loadingFinished":
                    # Проверяем, есть ли активные запросы
                    if await self.is_network_idle(session_id):
                        network_idle = True
                
                # Если и загрузка, и сеть бездействуют — страница готова
                if loaded and network_idle:
                    # Дополнительно ждём выполнения JS-фреймворков
                    await self.wait_for_js_frameworks(session_id, timeout=5)
                    return True
                    
            except asyncio.TimeoutError:
                continue
        
        # Если не дождались, но страница хоть как-то загрузилась
        return loaded
    
    async def is_network_idle(self, session_id):
        """Проверяет, есть ли активные сетевые запросы"""
        js = """
            (function() {
                return new Promise((resolve) => {
                    // Проверяем через Performance API
                    const entries = performance.getEntriesByType('resource');
                    const pending = entries.filter(e => 
                        e.responseEnd === 0 || e.responseStart === 0
                    );
                    resolve(pending.length === 0);
                });
            })()
        """
        return await self.evaluate(js, session_id)
    
    async def wait_for_js_frameworks(self, session_id, timeout=5):
        """Ожидание выполнения JS-фреймворков (React, Vue, Angular, etc.)"""
        js = """
            (function() {
                return new Promise((resolve) => {
                    const checkFrameworks = () => {
                        // Проверяем React
                        const hasReact = window.__REACT_DEVTOOLS_GLOBAL_HOOK__ !== undefined;
                        
                        // Проверяем Vue
                        const hasVue = window.__VUE_DEVTOOLS_GLOBAL_HOOK__ !== undefined;
                        
                        // Проверяем Angular
                        const hasAngular = window.ng !== undefined;
                        
                        // Проверяем, что DOM стабилен (нет мутаций)
                        let stable = true;
                        const observer = new MutationObserver(() => {
                            // Сбрасываем таймер при мутациях
                            clearTimeout(timeoutId);
                            stable = false;
                            setTimeout(() => {
                                stable = true;
                                resolve({hasReact, hasVue, hasAngular, stable});
                            }, 500);
                        });
                        
                        observer.observe(document.body, {
                            childList: true,
                            subtree: true,
                            attributes: true
                        });
                        
                        let timeoutId = setTimeout(() => {
                            observer.disconnect();
                            resolve({hasReact, hasVue, hasAngular, stable: true});
                        }, 2000);
                        
                        // Если нет фреймворков, просто ждём стабильности
                        if (!hasReact && !hasVue && !hasAngular) {
                            setTimeout(() => {
                                observer.disconnect();
                                resolve({hasReact, hasVue, hasAngular, stable: true});
                            }, 1000);
                        }
                    };
                    
                    if (document.readyState === 'complete') {
                        checkFrameworks();
                    } else {
                        window.addEventListener('load', checkFrameworks);
                    }
                });
            })()
        """
        return await self.evaluate(js, session_id)
    
    async def navigate(self, url, session_id):
        return await self.send("Page.navigate", {"url": url}, session_id)
    
    async def evaluate(self, expression, session_id, timeout=10):
        try:
            result = await asyncio.wait_for(
                self.send("Runtime.evaluate", {
                    "expression": expression,
                    "returnByValue": True
                }, session_id),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"JS timeout: {expression[:50]}")
        
        if "exceptionDetails" in result:
            raise RuntimeError(f"JS error: {result['exceptionDetails']}")
        
        return result.get("result", {}).get("value")
    
    # ==================== ИНТЕРАКТИВНЫЕ МЕТОДЫ ====================
    
    async def click(self, selector, session_id, wait_for_navigation=False):
        """Клик по элементу с опцией ожидания навигации"""
        # Проверяем видимость и кликаем
        js = f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return false;
                
                el.scrollIntoView({{block: 'center'}});
                
                // Эмулируем реальный клик
                const clickEvent = new MouseEvent('click', {{
                    view: window,
                    bubbles: true,
                    cancelable: true,
                    clientX: rect.x + rect.width/2,
                    clientY: rect.y + rect.height/2
                }});
                el.dispatchEvent(clickEvent);
                el.click(); // На всякий случай
                
                return true;
            }})()
        """
        result = await self.evaluate(js, session_id)
        
        # Если ожидаем навигацию после клика
        if wait_for_navigation and result:
            await self.wait_for_load(session_id, timeout=15)
        
        return result
    
    async def type_text(self, selector, text, session_id, clear_first=True):
        """Ввод текста в поле"""
        js = f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                
                el.scrollIntoView({{block: 'center'}});
                el.focus();
                
                if ({str(clear_first).lower()}) {{
                    el.value = '';
                }}
                
                // Вводим текст посимвольно для эмуляции реального ввода
                const chars = '{text}'.split('');
                for (let i = 0; i < chars.length; i++) {{
                    el.value += chars[i];
                    
                    // Триггерим события для React/Vue
                    const inputEvent = new Event('input', {{bubbles: true}});
                    el.dispatchEvent(inputEvent);
                    
                    const changeEvent = new Event('change', {{bubbles: true}});
                    el.dispatchEvent(changeEvent);
                }}
                
                return true;
            }})()
        """
        return await self.evaluate(js, session_id)
    
    async def select_option(self, selector, value, session_id):
        """Выбор опции в select"""
        js = f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                
                el.value = '{value}';
                const event = new Event('change', {{bubbles: true}});
                el.dispatchEvent(event);
                
                return true;
            }})()
        """
        return await self.evaluate(js, session_id)
    
    async def scroll_to(self, selector, session_id):
        """Скролл до элемента"""
        js = f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                el.scrollIntoView({{block: 'center', behavior: 'smooth'}});
                return true;
            }})()
        """
        return await self.evaluate(js, session_id)
    
    async def wait_for_element(self, selector, session_id, timeout=10, visible=True):
        """Ожидание появления элемента"""
        js = f"""
            new Promise((resolve) => {{
                const start = Date.now();
                const check = () => {{
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        if ({str(visible).lower()}) {{
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {{
                                resolve(true);
                                return;
                            }}
                        }} else {{
                            resolve(true);
                            return;
                        }}
                    }}
                    if (Date.now() - start > {timeout * 1000}) {{
                        resolve(false);
                        return;
                    }}
                    setTimeout(check, 200);
                }};
                check();
            }})
        """
        return await self.evaluate(js, session_id)
    
    async def wait_for_text(self, selector, text, session_id, timeout=10):
        """Ожидание появления текста в элементе"""
        js = f"""
            new Promise((resolve) => {{
                const start = Date.now();
                const check = () => {{
                    const el = document.querySelector('{selector}');
                    if (el && el.innerText && el.innerText.includes('{text}')) {{
                        resolve(true);
                        return;
                    }}
                    if (Date.now() - start > {timeout * 1000}) {{
                        resolve(false);
                        return;
                    }}
                    setTimeout(check, 200);
                }};
                check();
            }})
        """
        return await self.evaluate(js, session_id)
    
    async def wait_for_url(self, expected_url_part, session_id, timeout=10):
        """Ожидание изменения URL (для SPA)"""
        js = f"""
            new Promise((resolve) => {{
                const start = Date.now();
                const check = () => {{
                    const current = window.location.href;
                    if (current.includes('{expected_url_part}')) {{
                        resolve(true);
                        return;
                    }}
                    if (Date.now() - start > {timeout * 1000}) {{
                        resolve(false);
                        return;
                    }}
                    setTimeout(check, 200);
                }};
                check();
            }})
        """
        return await self.evaluate(js, session_id)
    
    async def take_screenshot(self, session_id, full_page=True):
        """Скриншот"""
        params = {
            "format": "png",
            "fromSurface": True,
            "captureBeyondViewport": full_page
        }
        result = await self.send("Page.captureScreenshot", params, session_id)
        return base64.b64decode(result["data"])
    
    async def get_page_text(self, session_id):
        """Весь текст страницы"""
        js = "document.body.innerText"
        return await self.evaluate(js, session_id)
    
    async def get_meta(self, session_id):
        """Метаданные страницы"""
        js = """
            (function() {
                return {
                    title: document.title,
                    url: window.location.href,
                    description: document.querySelector('meta[name="description"]')?.content || '',
                    keywords: document.querySelector('meta[name="keywords"]')?.content || ''
                }
            })()
        """
        return await self.evaluate(js, session_id)

# ==================== СЦЕНАРИИ ====================
class ScriptEngine:
    def __init__(self, cdp, session_id):
        self.cdp = cdp
        self.session_id = session_id
        self.steps = []
        self.results = []
    
    def add_step(self, action, **kwargs):
        """Добавляет шаг в сценарий"""
        self.steps.append({"action": action, **kwargs})
        return self
    
    async def run(self):
        """Выполняет сценарий"""
        for i, step in enumerate(self.steps):
            action = step.pop("action")
            result = await self._execute_action(action, step)
            self.results.append({"step": i, "action": action, "result": result})
        return self.results
    
    async def _execute_action(self, action, params):
        """Выполняет конкретное действие"""
        actions_map = {
            "click": self._action_click,
            "type": self._action_type,
            "select": self._action_select,
            "scroll": self._action_scroll,
            "wait_element": self._action_wait_element,
            "wait_text": self._action_wait_text,
            "wait_url": self._action_wait_url,
            "navigate": self._action_navigate,
            "screenshot": self._action_screenshot,
            "evaluate": self._action_evaluate,
        }
        
        func = actions_map.get(action)
        if not func:
            raise ValueError(f"Unknown action: {action}")
        
        return await func(**params)
    
    async def _action_click(self, selector, wait_for_navigation=False):
        return await self.cdp.click(selector, self.session_id, wait_for_navigation)
    
    async def _action_type(self, selector, text, clear_first=True):
        return await self.cdp.type_text(selector, text, self.session_id, clear_first)
    
    async def _action_select(self, selector, value):
        return await self.cdp.select_option(selector, value, self.session_id)
    
    async def _action_scroll(self, selector):
        return await self.cdp.scroll_to(selector, self.session_id)
    
    async def _action_wait_element(self, selector, timeout=10, visible=True):
        return await self.cdp.wait_for_element(selector, self.session_id, timeout, visible)
    
    async def _action_wait_text(self, selector, text, timeout=10):
        return await self.cdp.wait_for_text(selector, text, self.session_id, timeout)
    
    async def _action_wait_url(self, url_part, timeout=10):
        return await self.cdp.wait_for_url(url_part, self.session_id, timeout)
    
    async def _action_navigate(self, url):
        return await self.cdp.navigate(url, self.session_id)
    
    async def _action_screenshot(self, full_page=True):
        return await self.cdp.take_screenshot(self.session_id, full_page)
    
    async def _action_evaluate(self, js):
        return await self.cdp.evaluate(js, self.session_id)

# ==================== TELEGRAM BOT ====================
class BotHandler:
    def __init__(self):
        self.chrome = None
        self.cdp = None
        self.session_id = None
        self.current_url = None
        self.user_sessions = {}  # Храним сценарии пользователей
        
    async def init_chrome(self):
        self.chrome = ChromeManager()
        self.chrome.start()
        
        self.cdp = CDPController()
        await self.cdp.connect()
        print("✅ Бот готов")
    
    async def start_command(self, update, context):
        keyboard = [
            [InlineKeyboardButton("📸 Сделать снэпшот", callback_data="snapshot")],
            [InlineKeyboardButton("🎬 Запустить сценарий", callback_data="script")],
            [InlineKeyboardButton("📊 Проверить изменения", callback_data="compare")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🤖 *CDP Snapshot Bot*\n\n"
            "Я умею:\n"
            "📸 Делать полные снэпшоты страниц\n"
            "🎬 Выполнять интерактивные сценарии (клики, ввод)\n"
            "📊 Сравнивать снэпшоты и находить изменения\n"
            "⚡ Поддерживаю SPA (React, Vue, Angular)\n\n"
            "Просто отправь ссылку или выбери действие:",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    
    async def button_handler(self, update, context):
        query = update.callback_query
        await query.answer()
        
        if query.data == "snapshot":
            await query.edit_message_text(
                "📸 Отправь мне ссылку для создания снэпшота:\n"
                "Пример: `https://example.com`",
                parse_mode="Markdown"
            )
            context.user_data['mode'] = 'snapshot'
        
        elif query.data == "script":
            await query.edit_message_text(
                "🎬 *Интерактивный сценарий*\n\n"
                "Отправь команду в формате:\n"
                "`/script <url> | действие1 | действие2 | ...`\n\n"
                "*Доступные действия:*\n"
                "`click(selector)` - клик\n"
                "`type(selector, text)` - ввод текста\n"
                "`select(selector, value)` - выбор опции\n"
                "`wait(selector)` - ожидание элемента\n"
                "`wait_text(selector, text)` - ожидание текста\n"
                "`screenshot()` - скриншот\n\n"
                "*Пример:*\n"
                "`/script https://example.com | click(#login) | type(#email, test@mail.ru) | click(#submit)`",
                parse_mode="Markdown"
            )
            context.user_data['mode'] = 'script'
        
        elif query.data == "compare":
            await query.edit_message_text(
                "📊 *Сравнение снэпшотов*\n\n"
                "Отправь две ссылки через пробел:\n"
                "`/compare https://site.com/v1 https://site.com/v2`\n\n"
                "Или сравни с предыдущим снэпшотом:\n"
                "`/compare_last https://site.com`",
                parse_mode="Markdown"
            )
            context.user_data['mode'] = 'compare'
    
    async def handle_url(self, update, context):
        url = update.message.text.strip()
        mode = context.user_data.get('mode', 'snapshot')
        
        if not url.startswith(('http://', 'https://')):
            await update.message.reply_text("❌ Отправь корректную ссылку (с http:// или https://)")
            return
        
        if mode == 'snapshot':
            await self._handle_snapshot(update, url)
        elif mode == 'script':
            await update.message.reply_text("⚠️ Используй /script для сценариев")
        else:
            await self._handle_snapshot(update, url)
    
    async def _handle_snapshot(self, update, url):
        """Создание снэпшота"""
        await update.message.reply_text(f"🌐 Делаю снэпшот `{url}`...", parse_mode="Markdown")
        
        try:
            # Создаём вкладку
            await self.cdp.create_tab()
            session_id = await self.cdp.attach_to_tab()
            
            # Навигация
            await self.cdp.navigate(url, session_id)
            await update.message.reply_text("⏳ Загрузка страницы (включая SPA)...")
            
            # Ждём загрузку с поддержкой SPA
            if await self.cdp.wait_for_load(session_id, timeout=30):
                await update.message.reply_text("✅ Страница загружена!")
            else:
                await update.message.reply_text("⚠️ Частичная загрузка")
            
            # Делаем скриншот
            screenshot = await self.cdp.take_screenshot(session_id, full_page=True)
            
            # Сохраняем
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{SNAPSHOT_DIR}/snapshot_{timestamp}.png"
            with open(screenshot_path, "wb") as f:
                f.write(screenshot)
            
            # Отправляем скриншот
            with open(screenshot_path, "rb") as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=f"✅ Снэпшот готов!\n{url}\n📁 {screenshot_path}"
                )
            
            # Отправляем метаданные
            meta = await self.cdp.get_meta(session_id)
            await update.message.reply_text(
                f"📊 *Метаданные:*\n"
                f"📌 Title: {meta.get('title', 'Неизвестно')}\n"
                f"🔗 URL: {meta.get('url', url)}\n"
                f"📝 Description: {meta.get('description', 'Нет')[:100]}",
                parse_mode="Markdown"
            )
            
            # Закрываем вкладку
            await self.cdp.send("Target.closeTarget", {"targetId": self.cdp.target_id})
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: `{str(e)}`", parse_mode="Markdown")
    
    async def script_command(self, update, context):
        """Обработка интерактивного сценария"""
        text = update.message.text
        parts = text.split('|')
        
        if len(parts) < 2:
            await update.message.reply_text(
                "❌ Неверный формат.\n"
                "Используй: `/script <url> | действие1 | действие2 | ...`\n\n"
                "Пример: `/script https://example.com | click(#login) | type(#email, test@mail.ru)`",
                parse_mode="Markdown"
            )
            return
        
        # Парсим URL и действия
        url = parts[0].replace('/script', '').strip()
        actions = [a.strip() for a in parts[1:] if a.strip()]
        
        await update.message.reply_text(f"🎬 Запускаю сценарий для `{url}`", parse_mode="Markdown")
        
        try:
            # Создаём вкладку
            await self.cdp.create_tab()
            session_id = await self.cdp.attach_to_tab()
            
            # Навигация
            await self.cdp.navigate(url, session_id)
            await self.cdp.wait_for_load(session_id, timeout=30)
            
            # Создаём движок сценариев
            engine = ScriptEngine(self.cdp, session_id)
            
            # Разбираем действия
            for action_str in actions:
                await self._parse_and_execute(update, engine, action_str)
            
            # Финальный скриншот
            screenshot = await self.cdp.take_screenshot(session_id, full_page=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{SNAPSHOT_DIR}/script_result_{timestamp}.png"
            with open(screenshot_path, "wb") as f:
                f.write(screenshot)
            
            with open(screenshot_path, "rb") as f:
                await update.message.reply_photo(
                    photo=f,
                    caption="✅ *Сценарий выполнен!*\nФинальный скриншот",
                    parse_mode="Markdown"
                )
            
            # Закрываем вкладку
            await self.cdp.send("Target.closeTarget", {"targetId": self.cdp.target_id})
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка сценария: `{str(e)}`", parse_mode="Markdown")
    
    async def _parse_and_execute(self, update, engine, action_str):
        """Парсит и выполняет действие"""
        try:
            # Парсим действие (click(selector) или type(selector, text))
            if '(' in action_str and action_str.endswith(')'):
                action_name = action_str[:action_str.index('(')]
                params_str = action_str[action_str.index('(')+1:-1]
                
                # Разбираем параметры
                params = []
                current = ''
                in_quotes = False
                for char in params_str:
                    if char == '"' or char == "'":
                        in_quotes = not in_quotes
                    elif char == ',' and not in_quotes:
                        params.append(current.strip())
                        current = ''
                        continue
                    current += char
                if current:
                    params.append(current.strip())
                
                # Выполняем
                if action_name == "click":
                    selector = params[0].strip('"\'')
                    await engine.cdp.click(selector, engine.session_id, wait_for_navigation=True)
                    await update.message.reply_text(f"🖱️ Клик по `{selector}`", parse_mode="Markdown")
                
                elif action_name == "type":
                    selector = params[0].strip('"\'')
                    text = params[1].strip('"\'')
                    await engine.cdp.type_text(selector, text, engine.session_id)
                    await update.message.reply_text(f"⌨️ Ввод `{text}` в `{selector}`", parse_mode="Markdown")
                
                elif action_name == "select":
                    selector = params[0].strip('"\'')
                    value = params[1].strip('"\'')
                    await engine.cdp.select_option(selector, value, engine.session_id)
                    await update.message.reply_text(f"📋 Выбор `{value}` в `{selector}`", parse_mode="Markdown")
                
                elif action_name == "wait":
                    selector = params[0].strip('"\'')
                    await engine.cdp.wait_for_element(selector, engine.session_id)
                    await update.message.reply_text(f"⏳ Элемент `{selector}` появился", parse_mode="Markdown")
                
                elif action_name == "wait_text":
                    selector = params[0].strip('"\'')
                    text = params[1].strip('"\'')
                    await engine.cdp.wait_for_text(selector, text, engine.session_id)
                    await update.message.reply_text(f"📝 Текст `{text}` появился", parse_mode="Markdown")
                
                elif action_name == "screenshot":
                    screenshot = await engine.cdp.take_screenshot(engine.session_id, full_page=True)
                    path = f"{SNAPSHOT_DIR}/step_screenshot.png"
                    with open(path, "wb") as f:
                        f.write(screenshot)
                    with open(path, "rb") as f:
                        await update.message.reply_photo(photo=f, caption="📸 Промежуточный скриншот")
            
            else:
                await update.message.reply_text(f"⚠️ Неизвестное действие: {action_str}")
                
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка в действии `{action_str}`: {str(e)}", parse_mode="Markdown")
            raise
    
    async def compare_command(self, update, context):
        """Сравнение двух снэпшотов"""
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "❌ Используй: `/compare https://site.com/v1 https://site.com/v2`\n"
                "Или: `/compare_last https://site.com`",
                parse_mode="Markdown"
            )
            return
        
        if args[0] == 'last':
            url = args[1]
            await self._compare_with_last(update, url)
        else:
            url1, url2 = args[0], args[1]
            await self._compare_two(update, url1, url2)
    
    async def _compare_two(self, update, url1, url2):
        """Сравнивает две страницы"""
        await update.message.reply_text(f"📊 Сравниваю `{url1}` и `{url2}`...", parse_mode="Markdown")
        
        # Делаем снэпшоты
        snap1 = await self._make_snapshot_data(url1)
        snap2 = await self._make_snapshot_data(url2)
        
        if not snap1 or not snap2:
            await update.message.reply_text("❌ Не удалось загрузить страницы")
            return
        
        # Сравниваем
        diff = self._compare_snapshots(snap1, snap2)
        
        # Формируем отчёт
        message = (
            f"📊 *Сравнение снэпшотов*\n\n"
            f"🆚 {url1} vs {url2}\n"
            f"📏 Разница HTML: {diff['html_diff']:.1%}\n"
            f"🔗 Ссылки: {diff['links_changed']} изменений\n"
            f"🖼️ Изображения: {diff['images_changed']} изменений\n"
            f"📝 Текст: {diff['text_changed']} изменений\n\n"
            f"⚠️ *Основные изменения:*\n{diff['summary']}"
        )
        await update.message.reply_text(message, parse_mode="Markdown")
    
    async def _make_snapshot_data(self, url):
        """Делает снэпшот и возвращает данные"""
        try:
            await self.cdp.create_tab()
            session_id = await self.cdp.attach_to_tab()
            
            await self.cdp.navigate(url, session_id)
            await self.cdp.wait_for_load(session_id, timeout=30)
            
            html = await self.cdp.evaluate("document.documentElement.outerHTML", session_id)
            text = await self.cdp.get_page_text(session_id)
            links = await self.cdp.evaluate(
                "Array.from(document.querySelectorAll('a')).map(a => a.href)",
                session_id
            )
            images = await self.cdp.evaluate(
                "Array.from(document.querySelectorAll('img')).map(i => i.src)",
                session_id
            )
            
            await self.cdp.send("Target.closeTarget", {"targetId": self.cdp.target_id})
            
            return {
                "html": html,
                "text": text,
                "links": links or [],
                "images": images or []
            }
        except Exception as e:
            print(f"Error making snapshot: {e}")
            return None
    
    def _compare_snapshots(self, snap1, snap2):
        """Сравнивает два снэпшота"""
        # Сравнение HTML
        html_diff = difflib.SequenceMatcher(None, snap1['html'], snap2['html']).ratio()
        
        # Сравнение ссылок
        links1 = set(snap1['links'])
        links2 = set(snap2['links'])
        links_changed = len(links1.symmetric_difference(links2))
        
        # Сравнение изображений
        images1 = set(snap1['images'])
        images2 = set(snap2['images'])
        images_changed = len(images1.symmetric_difference(images2))
        
        # Сравнение текста
        text1 = snap1['text'].split()
        text2 = snap2['text'].split()
        text_diff = 1 - difflib.SequenceMatcher(None, text1, text2).ratio()
        
        # Формируем суммарное изменение
        changes = []
        if html_diff < 0.9:
            changes.append("📄 Изменён HTML")
        if links_changed > 0:
            changes.append(f"🔗 Изменилось {links_changed} ссылок")
        if images_changed > 0:
            changes.append(f"🖼️ Изменилось {images_changed} изображений")
        if text_diff > 0.1:
            changes.append("📝 Изменён текст")
        
        if not changes:
            changes.append("✅ Нет значительных изменений")
        
        return {
            "html_diff": 1 - html_diff,
            "links_changed": links_changed,
            "images_changed": images_changed,
            "text_changed": text_diff,
            "summary": "\n".join(changes)
        }
    
    async def shutdown(self):
        if self.cdp and self.cdp.ws:
            await self.cdp.ws.close()
        if self.chrome:
            self.chrome.stop()

# ==================== MAIN ====================
async def main():
    bot = BotHandler()
    await bot.init_chrome()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", bot.start_command))
    app.add_handler(CommandHandler("script", bot.script_command))
    app.add_handler(CommandHandler("compare", bot.compare_command))
    
    # Обработчики
    app.add_handler(CallbackQueryHandler(bot.button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_url))
    
    print("🚀 Бот запущен")
    try:
        await app.run_polling()
    finally:
        await bot.shutdown()

if __name__ == "__main__":
    asyncio.run(main())