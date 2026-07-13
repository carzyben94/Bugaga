# bot.py
import asyncio
import json
import os
import subprocess
import time
import base64
import hashlib
import difflib
import websockets
import aiohttp
from datetime import datetime
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "ВАШ_ТОКЕН")
CHROME_PATH = os.getenv("CHROME_PATH", "/usr/bin/google-chrome")
CDP_PORT = 9222
SNAPSHOT_DIR = "snapshots"
COMPARE_DIR = "comparisons"
LOG_FILE = "bot_logs.txt"

os.makedirs(SNAPSHOT_DIR, exist_ok=True)
os.makedirs(COMPARE_DIR, exist_ok=True)

# ==================== ЛОГИРОВАНИЕ ====================
class FileLogger:
    def __init__(self, filename=LOG_FILE):
        self.filename = filename
    
    def log(self, message, level="INFO"):
        """Запись лога в файл"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.filename, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] [{level}] {message}\n")
        except Exception as e:
            print(f"Ошибка записи лога: {e}")
    
    def info(self, message):
        self.log(message, "INFO")
    
    def error(self, message):
        self.log(message, "ERROR")
    
    def warning(self, message):
        self.log(message, "WARNING")
    
    def debug(self, message):
        self.log(message, "DEBUG")
    
    def get_logs(self, lines=100):
        """Получить последние N строк лога"""
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                return ''.join(all_lines[-lines:])
        except FileNotFoundError:
            return "Лог-файл пока не создан."
        except Exception as e:
            return f"Ошибка чтения лога: {e}"
    
    def clear_logs(self):
        """Очистить лог-файл"""
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                f.write("")
            return True
        except Exception as e:
            return False

file_logger = FileLogger()

# ==================== CHROME MANAGER ====================
class ChromeManager:
    def __init__(self):
        self.process = None
        self.port = CDP_PORT
    
    def start(self):
        file_logger.info(f"🚀 Запуск Chrome на порту {self.port}")
        cmd = [
            CHROME_PATH,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox",
            "--disable-software-rasterizer",
            "--window-size=1920,1080",
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            f"--remote-debugging-port={self.port}"
        ]
        
        file_logger.debug(f"Команда Chrome: {' '.join(cmd)}")
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            time.sleep(3)
            file_logger.info(f"✅ Chrome запущен (PID: {self.process.pid})")
            return self.port
        except Exception as e:
            file_logger.error(f"❌ Ошибка запуска Chrome: {str(e)}")
            raise
    
    def stop(self):
        if self.process:
            file_logger.info(f"🛑 Остановка Chrome (PID: {self.process.pid})")
            try:
                self.process.terminate()
                self.process.wait()
                file_logger.info("✅ Chrome остановлен")
            except Exception as e:
                file_logger.error(f"❌ Ошибка остановки Chrome: {str(e)}")
        else:
            file_logger.warning("⚠️ Chrome не был запущен")

# ==================== CDP CONTROLLER ====================
class CDPController:
    def __init__(self, port=CDP_PORT):
        self.port = port
        self.ws = None
        self.target_id = None
        self.msg_id = 0
        self._session_id = None
        
    async def connect(self):
        file_logger.info("🔌 Подключение к CDP...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{self.port}/json/version") as resp:
                    data = await resp.json()
                    ws_url = data["webSocketDebuggerUrl"]
                    file_logger.debug(f"WebSocket URL: {ws_url}")
            
            self.ws = await websockets.connect(ws_url)
            file_logger.info("✅ CDP подключен")
            return self
        except Exception as e:
            file_logger.error(f"❌ Ошибка подключения CDP: {str(e)}")
            raise
    
    async def send(self, method, params=None, session_id=None):
        self.msg_id += 1
        msg = {"id": self.msg_id, "method": method, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        
        file_logger.debug(f"📤 CDP отправка: {method} (ID: {self.msg_id})")
        
        try:
            await self.ws.send(json.dumps(msg))
        except Exception as e:
            file_logger.error(f"❌ Ошибка отправки CDP: {str(e)}")
            raise
        
        while True:
            try:
                response = json.loads(await self.ws.recv())
                if response.get("id") == self.msg_id:
                    if "error" in response:
                        file_logger.error(f"❌ CDP ошибка: {response['error']}")
                        raise RuntimeError(f"CDP error: {response['error']}")
                    file_logger.debug(f"📥 CDP ответ: {method} OK")
                    return response.get("result")
            except Exception as e:
                file_logger.error(f"❌ Ошибка получения ответа CDP: {str(e)}")
                raise
    
    async def create_tab(self, url="about:blank"):
        file_logger.info(f"📑 Создание вкладки: {url}")
        try:
            result = await self.send("Target.createTarget", {"url": url})
            self.target_id = result["targetId"]
            file_logger.info(f"✅ Вкладка создана: {self.target_id}")
            return self.target_id
        except Exception as e:
            file_logger.error(f"❌ Ошибка создания вкладки: {str(e)}")
            raise
    
    async def attach_to_tab(self, target_id=None):
        tid = target_id or self.target_id
        file_logger.info(f"🔗 Прикрепление к вкладке: {tid}")
        try:
            result = await self.send("Target.attachToTarget", {
                "targetId": tid,
                "flatten": True
            })
            session_id = result["sessionId"]
            self._session_id = session_id
            
            file_logger.debug("Включение доменов...")
            await self.send("Page.enable", session_id=session_id)
            await self.send("Runtime.enable", session_id=session_id)
            await self.send("DOM.enable", session_id=session_id)
            await self.send("Network.enable", session_id=session_id)
            await self.send("Log.enable", session_id=session_id)
            
            # Отключаем webdriver
            await self.evaluate(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
                session_id
            )
            
            file_logger.info(f"✅ Прикреплён к вкладке: {session_id}")
            return session_id
        except Exception as e:
            file_logger.error(f"❌ Ошибка прикрепления к вкладке: {str(e)}")
            raise
    
    async def wait_for_load(self, session_id, timeout=30):
        file_logger.info(f"⏳ Ожидание загрузки страницы (таймаут: {timeout}с)")
        start = time.time()
        loaded = False
        network_idle = False
        content_detected = False
        
        while time.time() - start < timeout:
            try:
                response = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=1))
                method = response.get("method")
                
                if method == "Page.loadEventFired":
                    loaded = True
                    file_logger.debug("✅ Событие Page.loadEventFired получено")
                
                if method == "Network.loadingFinished":
                    if await self.is_network_idle(session_id):
                        network_idle = True
                        file_logger.debug("✅ Сеть бездействует")
                
                if loaded:
                    title = await self.evaluate("document.title", session_id)
                    if title and len(title) > 0:
                        content_detected = True
                        file_logger.debug(f"✅ Заголовок страницы: {title}")
                    
                    has_captcha = await self.evaluate(
                        "document.body?.innerText?.includes('captcha') || document.body?.innerText?.includes('CAPTCHA') || document.querySelector('[id*=\"captcha\"]') !== null",
                        session_id
                    )
                    if has_captcha:
                        file_logger.warning("⚠️ Обнаружена капча!")
                        return False
                
                if loaded and network_idle and content_detected:
                    await self.wait_for_js_frameworks(session_id, timeout=5)
                    file_logger.info(f"✅ Страница загружена за {time.time() - start:.1f}с")
                    return True
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                file_logger.error(f"❌ Ошибка ожидания загрузки: {str(e)}")
        
        file_logger.warning(f"⚠️ Частичная загрузка после {timeout}с")
        return loaded and content_detected
    
    async def is_network_idle(self, session_id):
        js = """
            (function() {
                return new Promise((resolve) => {
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
        file_logger.debug("⏳ Ожидание JS-фреймворков...")
        js = """
            (function() {
                return new Promise((resolve) => {
                    const checkFrameworks = () => {
                        const hasReact = window.__REACT_DEVTOOLS_GLOBAL_HOOK__ !== undefined;
                        const hasVue = window.__VUE_DEVTOOLS_GLOBAL_HOOK__ !== undefined;
                        const hasAngular = window.ng !== undefined;
                        
                        let stable = true;
                        const observer = new MutationObserver(() => {
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
        result = await self.evaluate(js, session_id)
        file_logger.debug(f"✅ Фреймворки: {result}")
        return result
    
    async def navigate(self, url, session_id):
        file_logger.info(f"🌐 Переход по URL: {url}")
        try:
            result = await self.send("Page.navigate", {"url": url}, session_id)
            file_logger.info(f"✅ Навигация завершена")
            return result
        except Exception as e:
            file_logger.error(f"❌ Ошибка навигации: {str(e)}")
            raise
    
    async def evaluate(self, expression, session_id, timeout=10):
        file_logger.debug(f"📝 Выполнение JS: {expression[:50]}...")
        try:
            result = await asyncio.wait_for(
                self.send("Runtime.evaluate", {
                    "expression": expression,
                    "returnByValue": True
                }, session_id),
                timeout=timeout
            )
            
            if "exceptionDetails" in result:
                file_logger.error(f"❌ JS ошибка: {result['exceptionDetails']}")
                raise RuntimeError(f"JS error: {result['exceptionDetails']}")
            
            return result.get("result", {}).get("value")
        except asyncio.TimeoutError:
            file_logger.error(f"❌ Таймаут JS: {expression[:50]}")
            raise TimeoutError(f"JS timeout: {expression[:50]}")
        except Exception as e:
            file_logger.error(f"❌ Ошибка выполнения JS: {str(e)}")
            raise
    
    async def take_screenshot(self, session_id, full_page=True):
        file_logger.info(f"📸 Создание скриншота (full_page: {full_page})")
        try:
            params = {
                "format": "png",
                "fromSurface": True,
                "captureBeyondViewport": full_page
            }
            result = await self.send("Page.captureScreenshot", params, session_id)
            file_logger.info(f"✅ Скриншот создан (размер: {len(result['data'])} байт)")
            return base64.b64decode(result["data"])
        except Exception as e:
            file_logger.error(f"❌ Ошибка создания скриншота: {str(e)}")
            raise
    
    async def get_page_text(self, session_id):
        file_logger.debug("📝 Получение текста страницы")
        try:
            js = "document.body.innerText"
            result = await self.evaluate(js, session_id)
            file_logger.debug(f"✅ Получено {len(result)} символов текста")
            return result
        except Exception as e:
            file_logger.error(f"❌ Ошибка получения текста: {str(e)}")
            return ""
    
    async def get_meta(self, session_id):
        file_logger.debug("📊 Получение метаданных")
        try:
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
            result = await self.evaluate(js, session_id)
            file_logger.info(f"✅ Метаданные: Title: {result.get('title', 'Нет')}")
            return result
        except Exception as e:
            file_logger.error(f"❌ Ошибка получения метаданных: {str(e)}")
            return {}
    
    async def close_tab(self, target_id=None):
        tid = target_id or self.target_id
        if tid:
            file_logger.info(f"🔒 Закрытие вкладки: {tid}")
            try:
                await self.send("Target.closeTarget", {"targetId": tid})
                file_logger.info(f"✅ Вкладка закрыта")
            except Exception as e:
                file_logger.error(f"❌ Ошибка закрытия вкладки: {str(e)}")
    
    async def disconnect(self):
        file_logger.info("🔌 Отключение CDP...")
        try:
            if self.ws:
                await self.ws.close()
            file_logger.info("✅ CDP отключён")
        except Exception as e:
            file_logger.error(f"❌ Ошибка отключения CDP: {str(e)}")

# ==================== TELEGRAM BOT ====================
class BotHandler:
    def __init__(self):
        self.chrome = None
        self.cdp = None
        self.session_id = None
        self.current_url = None
        file_logger.info("🤖 Инициализация бота")
        
    async def init_chrome(self):
        file_logger.info("🚀 Инициализация Chrome...")
        try:
            self.chrome = ChromeManager()
            self.chrome.start()
            
            self.cdp = CDPController()
            await self.cdp.connect()
            file_logger.info("✅ Бот готов к работе")
        except Exception as e:
            file_logger.error(f"❌ Ошибка инициализации Chrome: {str(e)}")
            raise
    
    async def start_command(self, update, context):
        user = update.effective_user
        file_logger.info(f"📩 Команда /start от {user.username or user.id}")
        
        keyboard = [
            [InlineKeyboardButton("📸 Сделать снэпшот", callback_data="snapshot")],
            [InlineKeyboardButton("🎬 Запустить сценарий", callback_data="script")],
            [InlineKeyboardButton("📊 Проверить изменения", callback_data="compare")],
            [InlineKeyboardButton("📋 Скачать логи", callback_data="logs")],
            [InlineKeyboardButton("🗑️ Очистить логи", callback_data="clear_logs")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🤖 *CDP Snapshot Bot*\n\n"
            "Я умею:\n"
            "📸 Делать полные снэпшоты страниц\n"
            "🎬 Выполнять интерактивные сценарии (клики, ввод)\n"
            "📊 Сравнивать снэпшоты и находить изменения\n"
            "⚡ Поддерживаю SPA (React, Vue, Angular)\n"
            "📋 Веду лог всех действий\n\n"
            "Просто отправь ссылку или выбери действие:",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        file_logger.info("✅ Главное меню отправлено")
    
    async def button_handler(self, update, context):
        query = update.callback_query
        user = update.effective_user
        await query.answer()
        
        file_logger.info(f"📩 Кнопка '{query.data}' от {user.username or user.id}")
        
        if query.data == "snapshot":
            await query.edit_message_text(
                "📸 Отправь мне ссылку для создания снэпшота:\n"
                "Пример: `https://example.com`",
                parse_mode="Markdown"
            )
            context.user_data['mode'] = 'snapshot'
            file_logger.info("📸 Режим снэпшота активирован")
        
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
            file_logger.info("🎬 Режим сценария активирован")
        
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
            file_logger.info("📊 Режим сравнения активирован")
        
        elif query.data == "logs":
            await query.edit_message_text("📋 Загружаю логи...")
            await self._send_logs(update, context)
        
        elif query.data == "clear_logs":
            if file_logger.clear_logs():
                await query.edit_message_text("🗑️ Логи очищены!")
                file_logger.info("🗑️ Логи очищены пользователем")
            else:
                await query.edit_message_text("❌ Ошибка очистки логов")
    
    async def _send_logs(self, update, context):
        """Отправляет лог-файл пользователю"""
        try:
            log_content = file_logger.get_logs(500)  # Последние 500 строк
            
            if not log_content or log_content == "Лог-файл пока не создан.":
                await update.callback_query.message.reply_text("📋 Лог-файл пока пуст.")
                return
            
            # Отправляем как файл
            with open(LOG_FILE, 'rb') as f:
                await update.callback_query.message.reply_document(
                    document=f,
                    filename=f"bot_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    caption=f"📋 Логи бота ({time.strftime('%Y-%m-%d %H:%M:%S')})"
                )
            file_logger.info(f"📋 Логи отправлены пользователю {update.effective_user.username or update.effective_user.id}")
            
        except Exception as e:
            file_logger.error(f"❌ Ошибка отправки логов: {str(e)}")
            await update.callback_query.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def handle_url(self, update, context):
        url = update.message.text.strip()
        mode = context.user_data.get('mode', 'snapshot')
        user = update.effective_user
        
        file_logger.info(f"📩 Получен URL от {user.username or user.id}: {url} (режим: {mode})")
        
        if not url.startswith(('http://', 'https://')):
            file_logger.warning(f"❌ Неверный URL: {url}")
            await update.message.reply_text("❌ Отправь корректную ссылку (с http:// или https://)")
            return
        
        if mode == 'snapshot':
            await self._handle_snapshot(update, url)
        elif mode == 'script':
            await update.message.reply_text("⚠️ Используй /script для сценариев")
        else:
            await self._handle_snapshot(update, url)
    
    async def _handle_snapshot(self, update, url):
        """Создание ПОЛНОГО снэпшота со всеми данными"""
        user = update.effective_user
        file_logger.info(f"📸 Начало снэпшота для {url} от {user.username or user.id}")
        
        await update.message.reply_text(f"🌐 Делаю снэпшот `{url}`...", parse_mode="Markdown")
        
        try:
            await self.cdp.create_tab()
            session_id = await self.cdp.attach_to_tab()
            file_logger.info(f"📑 Вкладка создана для {url}")
            
            await self.cdp.navigate(url, session_id)
            await update.message.reply_text("⏳ Загрузка страницы...")
            
            if await self.cdp.wait_for_load(session_id, timeout=30):
                await update.message.reply_text("✅ Страница загружена!")
                file_logger.info(f"✅ Страница {url} загружена")
            else:
                await update.message.reply_text("⚠️ Частичная загрузка")
                file_logger.warning(f"⚠️ Частичная загрузка {url}")
            
            # ============ СОБИРАЕМ ВСЁ ============
            await update.message.reply_text("📊 Собираю все данные...")
            file_logger.info(f"📊 Сбор данных для {url}")
            
            # 1. Скриншот
            screenshot = await self.cdp.take_screenshot(session_id, full_page=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{SNAPSHOT_DIR}/snapshot_{timestamp}.png"
            with open(screenshot_path, "wb") as f:
                f.write(screenshot)
            file_logger.info(f"📸 Скриншот сохранён: {screenshot_path}")
            
            # 2. Метаданные
            meta = await self.cdp.get_meta(session_id)
            file_logger.info(f"📊 Метаданные: {meta.get('title', 'Нет')}")
            
            # 3. HTML
            html = await self.cdp.evaluate("document.documentElement.outerHTML", session_id)
            html_path = f"{SNAPSHOT_DIR}/snapshot_{timestamp}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            file_logger.info(f"📄 HTML сохранён: {len(html)} символов")
            
            # 4. Все ссылки
            links = await self.cdp.evaluate("""
                Array.from(document.querySelectorAll('a')).map(a => ({
                    href: a.href,
                    text: a.innerText.trim(),
                    target: a.target,
                    rel: a.rel
                })).filter(l => l.href)
            """, session_id)
            file_logger.info(f"🔗 Найдено ссылок: {len(links)}")
            
            # 5. Все изображения
            images = await self.cdp.evaluate("""
                Array.from(document.querySelectorAll('img')).map(img => ({
                    src: img.src,
                    alt: img.alt || '',
                    width: img.width,
                    height: img.height
                })).filter(i => i.src)
            """, session_id)
            file_logger.info(f"🖼️ Найдено изображений: {len(images)}")
            
            # 6. Заголовки
            headings = await self.cdp.evaluate("""
                (function() {
                    const result = {};
                    for (let i = 1; i <= 6; i++) {
                        const tag = 'H' + i;
                        result[tag] = Array.from(document.querySelectorAll(tag))
                            .map(el => el.innerText.trim())
                            .filter(t => t);
                    }
                    return result;
                })()
            """, session_id)
            total_headings = sum(len(v) for v in headings.values())
            file_logger.info(f"📑 Найдено заголовков: {total_headings}")
            
            # 7. Скрипты
            scripts = await self.cdp.evaluate("""
                Array.from(document.querySelectorAll('script')).map(s => ({
                    src: s.src || '',
                    type: s.type || '',
                    async: s.async,
                    defer: s.defer,
                    content: s.src ? '' : s.innerText.slice(0, 200)
                }))
            """, session_id)
            file_logger.info(f"📜 Найдено скриптов: {len(scripts)}")
            
            # 8. Стили
            styles = await self.cdp.evaluate("""
                Array.from(document.querySelectorAll('link[rel="stylesheet"], style')).map(s => ({
                    type: s.tagName === 'LINK' ? 'external' : 'inline',
                    href: s.href || '',
                    content: s.tagName === 'STYLE' ? s.innerText.slice(0, 200) : ''
                }))
            """, session_id)
            file_logger.info(f"🎨 Найдено стилей: {len(styles)}")
            
            # 9. Формы
            forms = await self.cdp.evaluate("""
                Array.from(document.querySelectorAll('form')).map(f => ({
                    action: f.action || '',
                    method: f.method || 'GET',
                    inputs: Array.from(f.querySelectorAll('input, textarea, select')).map(inp => ({
                        name: inp.name || '',
                        type: inp.type || '',
                        placeholder: inp.placeholder || '',
                        required: inp.required || false
                    }))
                }))
            """, session_id)
            file_logger.info(f"📋 Найдено форм: {len(forms)}")
            
            # 10. Текст
            text = await self.cdp.get_page_text(session_id)
            file_logger.info(f"📝 Текст: {len(text)} символов")
            
            # 11. Cookies
            cookies = await self.cdp.evaluate("document.cookie", session_id)
            file_logger.info(f"🍪 Cookies: {len(cookies)} символов")
            
            # 12. localStorage
            localStorage = await self.cdp.evaluate("""
                JSON.stringify(
                    Object.fromEntries(
                        Object.entries(localStorage)
                    )
                )
            """, session_id)
            file_logger.info(f"💾 localStorage: {len(localStorage)} байт")
            
            # 13. Performance метрики
            perf = await self.cdp.evaluate("""
                (function() {
                    const perf = performance.getEntriesByType('navigation')[0];
                    if (!perf) return {};
                    return {
                        domContentLoaded: perf.domContentLoadedEventEnd - perf.domContentLoadedEventStart,
                        load: perf.loadEventEnd - perf.loadEventStart,
                        domInteractive: perf.domInteractive,
                        domComplete: perf.domComplete
                    };
                })()
            """, session_id)
            file_logger.info(f"⚡ Performance: {perf}")
            
            # 14. Сохраняем JSON
            data = {
                "timestamp": timestamp,
                "url": url,
                "metadata": meta,
                "links": links,
                "images": images,
                "headings": headings,
                "scripts": scripts,
                "styles": styles,
                "forms": forms,
                "text_length": len(text),
                "cookies": cookies,
                "localStorage": localStorage,
                "performance": perf,
                "files": {
                    "screenshot": screenshot_path,
                    "html": html_path
                }
            }
            
            json_path = f"{SNAPSHOT_DIR}/snapshot_{timestamp}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            file_logger.info(f"💾 JSON сохранён: {json_path}")
            
            # ============ ОТПРАВЛЯЕМ ============
            with open(screenshot_path, "rb") as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=f"✅ Снэпшот готов!\n{url}"
                )
            
            message = (
                f"📊 *Собрано данных:*\n\n"
                f"📄 HTML: `{len(html):,}` символов\n"
                f"🔗 Ссылок: {len(links)}\n"
                f"🖼️ Изображений: {len(images)}\n"
                f"📝 Текст: `{len(text):,}` символов\n"
                f"📑 Заголовков: {total_headings}\n"
                f"📜 Скриптов: {len(scripts)}\n"
                f"🎨 Стилей: {len(styles)}\n"
                f"📋 Форм: {len(forms)}\n"
                f"🍪 Cookies: `{len(cookies)}`\n\n"
                f"📌 Title: {meta.get('title', 'Нет')}\n"
                f"📝 Description: {meta.get('description', 'Нет')[:100]}\n\n"
                f"⚡ DOMContentLoaded: {perf.get('domContentLoaded', 0):.0f}ms\n"
                f"🚀 Полная загрузка: {perf.get('load', 0):.0f}ms\n\n"
                f"💾 Сохранено:\n"
                f"`{screenshot_path}`\n"
                f"`{html_path}`\n"
                f"`{json_path}`"
            )
            await update.message.reply_text(message, parse_mode="Markdown")
            
            await self.cdp.close_tab()
            file_logger.info(f"✅ Снэпшот {url} завершён")
            
        except Exception as e:
            file_logger.error(f"❌ Ошибка снэпшота {url}: {str(e)}")
            await update.message.reply_text(f"❌ Ошибка: `{str(e)}`", parse_mode="Markdown")
    
    async def script_command(self, update, context):
        """Обработка интерактивного сценария"""
        user = update.effective_user
        text = update.message.text
        file_logger.info(f"🎬 Команда /script от {user.username or user.id}: {text[:50]}...")
        
        parts = text.split('|')
        
        if len(parts) < 2:
            await update.message.reply_text(
                "❌ Неверный формат.\n"
                "Используй: `/script <url> | действие1 | действие2 | ...`\n\n"
                "Пример: `/script https://example.com | click(#login) | type(#email, test@mail.ru)`",
                parse_mode="Markdown"
            )
            return
        
        url = parts[0].replace('/script', '').strip()
        actions = [a.strip() for a in parts[1:] if a.strip()]
        
        file_logger.info(f"🎬 Сценарий для {url}, действий: {len(actions)}")
        await update.message.reply_text(f"🎬 Запускаю сценарий для `{url}`", parse_mode="Markdown")
        
        try:
            await self.cdp.create_tab()
            session_id = await self.cdp.attach_to_tab()
            
            await self.cdp.navigate(url, session_id)
            await self.cdp.wait_for_load(session_id, timeout=30)
            
            for action_str in actions:
                await self._parse_and_execute(update, action_str, session_id)
            
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
            
            await self.cdp.close_tab()
            file_logger.info(f"✅ Сценарий {url} завершён")
            
        except Exception as e:
            file_logger.error(f"❌ Ошибка сценария: {str(e)}")
            await update.message.reply_text(f"❌ Ошибка сценария: `{str(e)}`", parse_mode="Markdown")
    
    async def _parse_and_execute(self, update, action_str, session_id):
        """Парсит и выполняет действие"""
        file_logger.debug(f"🎬 Выполнение действия: {action_str}")
        try:
            if '(' in action_str and action_str.endswith(')'):
                action_name = action_str[:action_str.index('(')]
                params_str = action_str[action_str.index('(')+1:-1]
                
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
                
                if action_name == "click":
                    selector = params[0].strip('"\'')
                    await self.cdp.click(selector, session_id, wait_for_navigation=True)
                    await update.message.reply_text(f"🖱️ Клик по `{selector}`", parse_mode="Markdown")
                    file_logger.info(f"🖱️ Клик по {selector}")
                
                elif action_name == "type":
                    selector = params[0].strip('"\'')
                    text = params[1].strip('"\'')
                    await self.cdp.type_text(selector, text, session_id)
                    await update.message.reply_text(f"⌨️ Ввод `{text}` в `{selector}`", parse_mode="Markdown")
                    file_logger.info(f"⌨️ Ввод в {selector}")
                
                elif action_name == "select":
                    selector = params[0].strip('"\'')
                    value = params[1].strip('"\'')
                    await self.cdp.select_option(selector, value, session_id)
                    await update.message.reply_text(f"📋 Выбор `{value}` в `{selector}`", parse_mode="Markdown")
                
                elif action_name == "wait":
                    selector = params[0].strip('"\'')
                    await self.cdp.wait_for_element(selector, session_id)
                    await update.message.reply_text(f"⏳ Элемент `{selector}` появился", parse_mode="Markdown")
                
                elif action_name == "wait_text":
                    selector = params[0].strip('"\'')
                    text = params[1].strip('"\'')
                    await self.cdp.wait_for_text(selector, text, session_id)
                    await update.message.reply_text(f"📝 Текст `{text}` появился", parse_mode="Markdown")
                
                elif action_name == "screenshot":
                    screenshot = await self.cdp.take_screenshot(session_id, full_page=True)
                    path = f"{SNAPSHOT_DIR}/step_screenshot.png"
                    with open(path, "wb") as f:
                        f.write(screenshot)
                    with open(path, "rb") as f:
                        await update.message.reply_photo(photo=f, caption="📸 Промежуточный скриншот")
                    file_logger.info("📸 Промежуточный скриншот")
            
            else:
                file_logger.warning(f"⚠️ Неизвестное действие: {action_str}")
                await update.message.reply_text(f"⚠️ Неизвестное действие: {action_str}")
                
        except Exception as e:
            file_logger.error(f"❌ Ошибка в действии {action_str}: {str(e)}")
            await update.message.reply_text(f"❌ Ошибка в действии `{action_str}`: {str(e)}", parse_mode="Markdown")
            raise
    
    async def compare_command(self, update, context):
        """Сравнение двух снэпшотов"""
        user = update.effective_user
        args = context.args
        file_logger.info(f"📊 Команда /compare от {user.username or user.id}: {args}")
        
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
        user = update.effective_user
        file_logger.info(f"📊 Сравнение {url1} vs {url2} от {user.username or user.id}")
        
        await update.message.reply_text(f"📊 Сравниваю `{url1}` и `{url2}`...", parse_mode="Markdown")
        
        snap1 = await self._make_snapshot_data(url1)
        snap2 = await self._make_snapshot_data(url2)
        
        if not snap1 or not snap2:
            await update.message.reply_text("❌ Не удалось загрузить страницы")
            return
        
        diff = self._compare_snapshots(snap1, snap2)
        
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
        file_logger.info(f"📊 Сравнение завершено")
    
    async def _make_snapshot_data(self, url):
        """Делает снэпшот и возвращает данные"""
        file_logger.info(f"📸 Создание данных для сравнения: {url}")
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
            
            await self.cdp.close_tab()
            
            file_logger.info(f"✅ Данные для {url} созданы")
            return {
                "html": html,
                "text": text,
                "links": links or [],
                "images": images or []
            }
        except Exception as e:
            file_logger.error(f"❌ Ошибка создания данных для {url}: {str(e)}")
            return None
    
    def _compare_snapshots(self, snap1, snap2):
        """Сравнивает два снэпшота"""
        html_diff = difflib.SequenceMatcher(None, snap1['html'], snap2['html']).ratio()
        
        links1 = set(snap1['links'])
        links2 = set(snap2['links'])
        links_changed = len(links1.symmetric_difference(links2))
        
        images1 = set(snap1['images'])
        images2 = set(snap2['images'])
        images_changed = len(images1.symmetric_difference(images2))
        
        text1 = snap1['text'].split()
        text2 = snap2['text'].split()
        text_diff = 1 - difflib.SequenceMatcher(None, text1, text2).ratio()
        
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
    
    async def compare_with_last(self, update, url):
        """Сравнивает с предыдущим снэпшотом"""
        # Находим последний снэпшот
        try:
            files = [f for f in os.listdir(SNAPSHOT_DIR) if f.startswith('snapshot_') and f.endswith('.json')]
            if not files:
                await update.message.reply_text("❌ Нет сохранённых снэпшотов")
                return
            
            latest = sorted(files)[-1]
            with open(os.path.join(SNAPSHOT_DIR, latest), 'r', encoding='utf-8') as f:
                old_data = json.load(f)
            
            await update.message.reply_text(f"📊 Сравниваю с предыдущим снэпшотом: {latest}")
            
            # Делаем новый снэпшот
            new_data = await self._make_snapshot_data(url)
            if not new_data:
                await update.message.reply_text("❌ Не удалось загрузить страницу")
                return
            
            # Сравниваем
            diff = self._compare_snapshots(
                {
                    "html": old_data.get("html", ""),
                    "text": old_data.get("text", ""),
                    "links": old_data.get("links", []),
                    "images": old_data.get("images", [])
                },
                new_data
            )
            
            message = (
                f"📊 *Сравнение с предыдущим снэпшотом*\n\n"
                f"🆚 {old_data.get('url', 'Неизвестно')} vs {url}\n"
                f"📏 Разница HTML: {diff['html_diff']:.1%}\n"
                f"🔗 Ссылки: {diff['links_changed']} изменений\n"
                f"🖼️ Изображения: {diff['images_changed']} изменений\n"
                f"📝 Текст: {diff['text_changed']} изменений\n\n"
                f"⚠️ *Основные изменения:*\n{diff['summary']}"
            )
            await update.message.reply_text(message, parse_mode="Markdown")
            file_logger.info(f"📊 Сравнение с предыдущим завершено")
            
        except Exception as e:
            file_logger.error(f"❌ Ошибка сравнения: {str(e)}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def shutdown(self):
        file_logger.info("🛑 Завершение работы бота...")
        try:
            if self.cdp:
                await self.cdp.disconnect()
            if self.chrome:
                self.chrome.stop()
            file_logger.info("✅ Бот остановлен")
        except Exception as e:
            file_logger.error(f"❌ Ошибка завершения: {str(e)}")

# ==================== MAIN ====================
def main():
    """Точка входа с правильным управлением event loop"""
    file_logger.info("🚀 ЗАПУСК БОТА")
    file_logger.info(f"📁 Папка снэпшотов: {SNAPSHOT_DIR}")
    file_logger.info(f"📁 Лог-файл: {LOG_FILE}")
    file_logger.info(f"🔑 TELEGRAM_TOKEN: {'Установлен' if TELEGRAM_TOKEN != 'ВАШ_ТОКЕН' else 'НЕ УСТАНОВЛЕН'}")
    
    bot = BotHandler()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", bot.start_command))
    app.add_handler(CommandHandler("script", bot.script_command))
    app.add_handler(CommandHandler("compare", bot.compare_command))
    app.add_handler(CommandHandler("compare_last", bot.compare_with_last))
    app.add_handler(CallbackQueryHandler(bot.button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_url))
    
    file_logger.info("✅ Обработчики зарегистрированы")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(bot.init_chrome())
        file_logger.info("🚀 Бот запущен и готов к работе!")
        loop.run_until_complete(app.run_polling())
        
    except KeyboardInterrupt:
        file_logger.info("🛑 Остановка бота (Ctrl+C)...")
    except Exception as e:
        file_logger.error(f"❌ Критическая ошибка: {str(e)}")
    finally:
        try:
            loop.run_until_complete(bot.shutdown())
        except:
            pass
        loop.close()
        file_logger.info("✅ Бот остановлен")

if __name__ == "__main__":
    main()