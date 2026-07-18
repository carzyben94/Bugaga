import os
import sys
import asyncio
import json
import time
import subprocess
import shutil
import logging
from typing import Optional, Dict, Any, List, Union

# ===== НАСТРОЙКА ЛОГГИРОВАНИЯ =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ =====
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN не задан")
    sys.exit(1)

# ===== УНИВЕРСАЛЬНЫЙ ИМПОРТ BROWSER-HARNESS =====
HARNESS_AVAILABLE = False
BH = None
BH_CDP = None
BH_HELPERS = None

try:
    # Пробуем импортировать browser-harness
    import browser_harness
    logger.info(f"📦 browser-harness загружен: {browser_harness.__file__}")
    
    # Сохраняем ссылку на модуль
    BH = browser_harness
    
    # Пробуем разные способы доступа к функциям
    if hasattr(browser_harness, 'helpers'):
        BH_HELPERS = browser_harness.helpers
        logger.info("✅ Использую browser_harness.helpers")
    
    if hasattr(browser_harness, 'cdp'):
        BH_CDP = browser_harness.cdp
        logger.info("✅ Использую browser_harness.cdp")
    
    # Если helpers не найден, пробуем импортировать напрямую
    if BH_HELPERS is None:
        try:
            from browser_harness import helpers
            BH_HELPERS = helpers
            logger.info("✅ Использую helpers напрямую")
        except ImportError:
            pass
    
    # Если cdp не найден, пробуем через helpers
    if BH_CDP is None and BH_HELPERS is not None:
        if hasattr(BH_HELPERS, 'cdp'):
            BH_CDP = BH_HELPERS.cdp
    
    HARNESS_AVAILABLE = True
    logger.info(f"📋 Доступно: {[x for x in dir(BH) if not x.startswith('_')][:5]}...")
    
except ImportError as e:
    logger.warning(f"⚠️ browser-harness не найден: {e}")
    HARNESS_AVAILABLE = False

# ===== ИМПОРТ TELEGRAM =====
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError as e:
    logger.error(f"❌ Ошибка импорта telegram: {e}")
    TELEGRAM_AVAILABLE = False
    sys.exit(1)

# ===== ИМПОРТ HTTP =====
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning("⚠️ httpx не установлен")

# ===== УНИВЕРСАЛЬНЫЙ ВЫЗОВ ФУНКЦИЙ =====
def call_bh(func_name: str, *args, **kwargs) -> Any:
    """
    Универсальный вызов функций browser-harness
    """
    if not HARNESS_AVAILABLE:
        raise ImportError("browser-harness не доступен")
    
    # Пробуем в helpers
    if BH_HELPERS is not None and hasattr(BH_HELPERS, func_name):
        return getattr(BH_HELPERS, func_name)(*args, **kwargs)
    
    # Пробуем в cdp
    if BH_CDP is not None and hasattr(BH_CDP, func_name):
        return getattr(BH_CDP, func_name)(*args, **kwargs)
    
    # Пробуем в основном модуле
    if BH is not None and hasattr(BH, func_name):
        return getattr(BH, func_name)(*args, **kwargs)
    
    # Пробуем через cdp напрямую
    if BH_CDP is not None and func_name == 'cdp':
        return BH_CDP(*args, **kwargs)
    
    raise AttributeError(f"Функция {func_name} не найдена в browser-harness")

# ===== ПРОВЕРКА БРАУЗЕРА =====
def check_browser(port: int = 9222) -> bool:
    """Проверяет, доступен ли браузер на порту 9222"""
    if not HTTPX_AVAILABLE:
        return False
    try:
        resp = httpx.get(f"http://localhost:{port}/json/version", timeout=2)
        return resp.status_code == 200
    except:
        return False

def wait_for_browser(timeout: int = 15, port: int = 9222) -> bool:
    """Ждёт, пока браузер станет доступен"""
    if not HTTPX_AVAILABLE:
        return False
    for attempt in range(timeout):
        try:
            resp = httpx.get(f"http://localhost:{port}/json/version", timeout=1)
            if resp.status_code == 200:
                logger.info(f"✅ Браузер готов ({attempt+1}s)")
                return True
        except:
            pass
        time.sleep(1)
        logger.info(f"⏳ Ожидание браузера... ({attempt+1}/{timeout})")
    logger.error("❌ Браузер не запустился!")
    return False

# ===== УНИВЕРСАЛЬНЫЙ КЛАСС БРАУЗЕРА =====
class UniversalBrowser:
    """Универсальный класс для работы с браузером через browser-harness"""
    
    def __init__(self):
        self.connected = False
        self.ws = None
        self._msg_id = 0
    
    async def connect(self) -> Union[str, bool]:
        """Подключение к браузеру"""
        if not HARNESS_AVAILABLE:
            return "❌ browser-harness не доступен"
        
        # Проверяем браузер
        if not check_browser():
            return "❌ Браузер не запущен"
        
        try:
            # Пробуем разные способы
            if BH_HELPERS is not None and hasattr(BH_HELPERS, 'ensure_real_tab'):
                BH_HELPERS.ensure_real_tab()
                self.connected = True
                logger.info("✅ Подключен через helpers.ensure_real_tab")
                return "✅ Подключен"
            
            if BH_HELPERS is not None and hasattr(BH_HELPERS, 'ensure_tab'):
                BH_HELPERS.ensure_tab()
                self.connected = True
                logger.info("✅ Подключен через helpers.ensure_tab")
                return "✅ Подключен"
            
            # Пробуем через cdp
            ws_url = self._get_ws_url()
            if ws_url:
                import websockets
                self.ws = await websockets.connect(ws_url)
                self.connected = True
                logger.info("✅ Подключен через WebSocket")
                return "✅ Подключен"
            
            return "❌ Не удалось подключиться"
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            return f"❌ Ошибка: {e}"
    
    def _get_ws_url(self) -> Optional[str]:
        """Получает WebSocket URL от браузера"""
        if not HTTPX_AVAILABLE:
            return None
        try:
            resp = httpx.get("http://localhost:9222/json/version", timeout=2)
            return resp.json().get("webSocketDebuggerUrl")
        except:
            return None
    
    async def send_command(self, method: str, params: Dict = None) -> Dict:
        """Отправка CDP-команды"""
        if not self.connected or self.ws is None:
            return {"error": "Не подключен"}
        
        try:
            self._msg_id += 1
            msg = {"id": self._msg_id, "method": method, "params": params or {}}
            await self.ws.send(json.dumps(msg))
            
            while True:
                response = await self.ws.recv()
                data = json.loads(response)
                if data.get("id") == self._msg_id:
                    if "error" in data:
                        return {"error": data["error"]}
                    return data.get("result", {})
        except Exception as e:
            return {"error": str(e)}
    
    async def navigate(self, url: str) -> Dict:
        """Переход по URL"""
        if not self.connected:
            result = await self.connect()
            if isinstance(result, str) and result.startswith("❌"):
                return {"success": False, "error": result}
        
        try:
            # Пробуем через helpers
            if BH_HELPERS is not None and hasattr(BH_HELPERS, 'goto_url'):
                BH_HELPERS.goto_url(url)
                return {"success": True, "url": url}
            
            # Через CDP
            result = await self.send_command("Page.navigate", {"url": url})
            if "error" in result:
                return {"success": False, "error": result["error"]}
            
            # Ждём загрузки
            for attempt in range(20):
                ready = await self.evaluate("document.readyState")
                if ready == "complete":
                    break
                await asyncio.sleep(0.5)
            
            return {"success": True, "url": url}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def evaluate(self, expression: str) -> Any:
        """Выполнение JavaScript"""
        if not self.connected:
            result = await self.connect()
            if isinstance(result, str) and result.startswith("❌"):
                return {"error": result}
        
        try:
            # Пробуем через helpers
            if BH_HELPERS is not None and hasattr(BH_HELPERS, 'js'):
                return BH_HELPERS.js(expression)
            
            # Через CDP
            result = await self.send_command("Runtime.evaluate", {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            })
            
            if "error" in result:
                return {"error": result["error"]}
            
            return result.get("result", {}).get("value")
            
        except Exception as e:
            return {"error": str(e)}
    
    async def screenshot(self) -> Union[bytes, Dict]:
        """Скриншот страницы"""
        if not self.connected:
            result = await self.connect()
            if isinstance(result, str) and result.startswith("❌"):
                return {"error": result}
        
        try:
            # Пробуем через helpers
            if BH_HELPERS is not None and hasattr(BH_HELPERS, 'capture_screenshot'):
                import tempfile
                path = tempfile.mktemp(suffix=".png")
                BH_HELPERS.capture_screenshot(path)
                with open(path, "rb") as f:
                    return f.read()
            
            # Через CDP
            result = await self.send_command("Page.captureScreenshot", {"format": "png"})
            if "error" in result:
                return {"error": result["error"]}
            
            import base64
            return base64.b64decode(result.get("data", ""))
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_info(self) -> Dict:
        """Получение информации о странице"""
        if not self.connected:
            result = await self.connect()
            if isinstance(result, str) and result.startswith("❌"):
                return {"error": result}
        
        try:
            if BH_HELPERS is not None and hasattr(BH_HELPERS, 'page_info'):
                return BH_HELPERS.page_info()
            
            title = await self.evaluate("document.title")
            url = await self.evaluate("window.location.href")
            return {"title": title, "url": url}
            
        except Exception as e:
            return {"error": str(e)}

# ===== СОЗДАЁМ ЭКЗЕМПЛЯР БРАУЗЕРА =====
browser = UniversalBrowser()

# ===== ИМПОРТ TELEGRAM (уже сделан выше) =====
# Продолжаем с командами бота...