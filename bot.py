import os
import sys
import asyncio
import importlib
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WS_URL = os.getenv("HARNESS_WS_URL", "ws://localhost:9222/devtools/browser")

# ============ УНИВЕРСАЛЬНЫЙ ИМПОРТ ============
def get_harness_class():
    """
    Автоматически находит правильный класс Harness в пакете
    """
    try:
        import browser_harness
        
        # Проверяем все атрибуты пакета
        for attr_name in dir(browser_harness):
            if attr_name.lower() in ['harness', 'browserharness', 'cdpharness']:
                attr = getattr(browser_harness, attr_name)
                if callable(attr):
                    return attr
        
        # Пробуем импортировать из подмодулей
        submodules = ['harness', 'core', 'browser', 'cdp', 'client']
        for sub in submodules:
            try:
                module = importlib.import_module(f'browser_harness.{sub}')
                for attr_name in dir(module):
                    if attr_name.lower() in ['harness', 'browserharness']:
                        attr = getattr(module, attr_name)
                        if callable(attr):
                            return attr
            except ImportError:
                continue
        
        # Если ничего не найдено - выводим структуру
        print("📦 Содержимое browser_harness:")
        print(dir(browser_harness))
        
        # Проверяем, есть ли вложенные пакеты
        if hasattr(browser_harness, '__path__'):
            import pkgutil
            print("\n📁 Подмодули:")
            for module_info in pkgutil.iter_modules(browser_harness.__path__):
                print(f"  - {module_info.name}")
        
        return None
        
    except ImportError as e:
        print(f"❌ Не удалось импортировать browser_harness: {e}")
        return None

# Получаем класс
HarnessClass = get_harness_class()

if HarnessClass is None:
    print("❌ Harness не найден. Используем fallback - прямую работу с CDP")
    HarnessClass = None

# ============ FALLBACK - ПРЯМОЙ CDP ============
class SimpleCDP:
    """Запасной вариант без browser-harness"""
    
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.ws = None
        self.message_id = 0
        self.tabs = {}
        
    async def connect(self):
        import websockets
        self.ws = await websockets.connect(self.ws_url)
        print(f"✅ CDP подключен к {self.ws_url}")
        return self
    
    async def send(self, method, params=None, session_id=None):
        self.message_id += 1
        msg = {
            "id": self.message_id,
            "method": method,
            "params": params or {}
        }
        if session_id:
            msg["sessionId"] = session_id
        await self.ws.send(json.dumps(msg))
        response = await self.ws.recv()
        return json.loads(response)
    
    async def new_tab(self):
        result = await self.send("Target.createTarget", {"url": "about:blank"})
        target_id = result['result']['targetId']
        
        # Получаем сессию для новой вкладки
        session_result = await self.send("Target.attachToTarget", {"targetId": target_id})
        session_id = session_result['result']['sessionId']
        
        tab = SimpleTab(self, session_id)
        self.tabs[target_id] = tab
        return tab
    
    async def close_tab(self, target_id):
        await self.send("Target.closeTarget", {"targetId": target_id})
        del self.tabs[target_id]

class SimpleTab:
    def __init__(self, cdp, session_id):
        self.cdp = cdp
        self.session_id = session_id
        
    async def goto(self, url):
        await self.cdp.send("Page.navigate", {"url": url}, self.session_id)
        
    async def screenshot(self):
        result = await self.cdp.send("Page.captureScreenshot", {"format": "png"}, self.session_id)
        import base64
        return base64.b64decode(result['result']['data'])
    
    async def content(self):
        result = await self.cdp.send("Runtime.evaluate", {
            "expression": "document.documentElement.outerHTML"
        }, self.session_id)
        return result['result']['result']['value']
    
    async def close(self):
        # Получаем targetId из session_id
        for target_id, tab in self.cdp.tabs.items():
            if tab is self:
                await self.cdp.close_tab(target_id)
                break

# ============ ИНИЦИАЛИЗАЦИЯ ============
class BrowserManager:
    def __init__(self):
        self.harness = None
        self.is_cdp = False
        
    async def init(self):
        if HarnessClass:
            try:
                # Пробуем стандартный способ
                if hasattr(HarnessClass, 'connect'):
                    self.harness = await HarnessClass.connect(WS_URL)
                else:
                    self.harness = HarnessClass(WS_URL)
                    if hasattr(self.harness, 'connect'):
                        await self.harness.connect()
                print("✅ Harness инициализирован")
                return self.harness
            except Exception as e:
                print(f"⚠️ Ошибка Harness: {e}, переключаемся на CDP")
        
        # Fallback на CDP
        self.is_cdp = True
        self.harness = SimpleCDP(WS_URL)
        await self.harness.connect()
        return self.harness
    
    async def new_tab(self):
        if hasattr(self.harness, 'new_tab'):
            return await self.harness.new_tab()
        elif hasattr(self.harness, 'create_tab'):
            return await self.harness.create_tab()
        elif hasattr(self.harness, 'newPage'):
            return await self.harness.newPage()
        else:
            raise Exception("Не найден метод создания вкладки")
    
    async def close(self):
        if hasattr(self.harness, 'close'):
            await self.harness.close()
        elif hasattr(self.harness, 'ws') and self.harness.ws:
            await self.harness.ws.close()

browser_manager = BrowserManager()

# ============ BOT COMMANDS ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Browser Harness Bot\n"
        "Команды:\n"
        "/navigate <url> - открыть страницу\n"
        "/screenshot - скриншот\n"
        "/html - получить HTML\n"
        "/close - закрыть вкладку"
    )

async def navigate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажите URL")
        return
    
    url = context.args[0]
    try:
        tab = await browser_manager.new_tab()
        await tab.goto(url)
        context.user_data['tab'] = tab
        await update.message.reply_text(f"✅ Открыто: {url}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tab = context.user_data.get('tab')
    if not tab:
        await update.message.reply_text("❌ Нет активной вкладки")
        return
    
    try:
        img = await tab.screenshot()
        await update.message.reply_photo(img)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def get_html(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tab = context.user_data.get('tab')
    if not tab:
        await update.message.reply_text("❌ Нет активной вкладки")
        return
    
    try:
        html = await tab.content()
        await update.message.reply_text(html[:4000])
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def close_tab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tab = context.user_data.get('tab')
    if tab:
        try:
            await tab.close()
            context.user_data['tab'] = None
            await update.message.reply_text("✅ Вкладка закрыта")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    else:
        await update.message.reply_text("Нет активной вкладки")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_text = f"""
📊 Статус:
- Harness: {'✅' if browser_manager.harness else '❌'}
- Режим: {'CDP прямой' if browser_manager.is_cdp else 'browser-harness'}
- Активная вкладка: {'✅' if context.user_data.get('tab') else '❌'}
- WS URL: {WS_URL}
    """
    await update.message.reply_text(status_text)

# ============ MAIN ============
def main():
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN не установлен")
        sys.exit(1)
    
    # Инициализируем браузер
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(browser_manager.init())
    
    if not browser_manager.harness:
        print("❌ Не удалось инициализировать браузер")
        sys.exit(1)
    
    # Бот
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("navigate", navigate))
    app.add_handler(CommandHandler("screenshot", screenshot))
    app.add_handler(CommandHandler("html", get_html))
    app.add_handler(CommandHandler("close", close_tab))
    app.add_handler(CommandHandler("status", status))
    
    print("🤖 Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()