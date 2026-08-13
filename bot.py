import os
import sys
import asyncio
import logging
import subprocess
import time
import json
import base64
import io
import random
import math
from contextlib import redirect_stdout, asynccontextmanager
from datetime import datetime
from typing import Optional, Union, List, Dict, Any
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================
# ДОБАВЛЯЕМ ЛОКАЛЬНЫЙ browser-harness
# ============================================

sys.path.insert(0, "browser-harness/src")

# ============================================
# ИМПОРТЫ BROWSER HARNESS
# ============================================

from browser_harness.helpers import (
    new_tab,
    goto_url,
    wait_for_load,
    close_tab,
    page_info,
    current_tab,
    capture_screenshot,
    js,
    list_tabs,
    switch_tab,
    fill_input,
    click_at_xy,
    type_text,
    press_key,
    scroll,
    cdp,
    ensure_real_tab,
)
from browser_harness.admin import ensure_daemon

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не установлен!")

# ============================================
# КУКИ ДЛЯ X.COM (TWITTER)
# ============================================

COOKIES = [
    {
        "name": "__cuid",
        "value": "55d2d7c5-4888-430a-b024-dd785da46ef4",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "personalization_id",
        "value": "\"v1_VL5PDSWqcwv7LNBV75SiLA==\"",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "g_state",
        "value": "{\"i_l\":0,\"i_ll\":1786493441069,\"i_b\":\"GK5KqYSRaGCT7CvSxBv3wqY6m7ne53iSPqkYW+ROGIo\",\"i_e\":{\"enable_itp_optimization\":24},\"i_et\":1786493441069}",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "lang",
        "value": "ru",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "dnt",
        "value": "1",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "gt",
        "value": "2087858962263671253",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "guest_id",
        "value": "v1%3A178661934178349765",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "twid",
        "value": "u%3D2075158859295997952",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "auth_token",
        "value": "c67259d770166a76598c693d9536c5356f521343",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "guest_id_ads",
        "value": "v1%3A178661934178349765",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "guest_id_marketing",
        "value": "v1%3A178661934178349765",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "ct0",
        "value": "a7588aaf794885b9e039dc7b81874e17e2786d50a7ba5794412780256f819111535e58b52f13fd571176e7b3d3ceb79a95aa722288c8811a4cfb02ff4a9ecf2f36e0ab11032d6aab77df44902a0d2715",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    },
    {
        "name": "__cf_bm",
        "value": ".WtFBy2_JUO1VAFxh4adk0Ke7.8T0w0MZNBftx1Y7Og-1786619407.2810972-1.0.1.1-V7njqiTJRq5SKwLgiqsE6SGR1qScNXtusMEP1ii5Ai24nxQMM76kNpVeVXYPE4zyY4gLtQKmQCdFCgdsuocz2NxkGJq.ku2bfEopXW73Ywm6wVrXxc0LnxPRWbV.vXZI",
        "domain": ".x.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "unspecified"
    }
]

# ============================================
# ПРОВЕРКА КОМПОНЕНТОВ
# ============================================

def check_veil():
    try:
        import veilbrowser
        return True, getattr(veilbrowser, '__version__', 'unknown')
    except ImportError:
        return False, None

def check_chrome():
    paths = ["/usr/bin/chromium", "/usr/bin/google-chrome", "/usr/bin/chrome"]
    for p in paths:
        if os.path.exists(p):
            return p
    try:
        result = subprocess.run(['which', 'chromium'], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except:
        pass
    return None

VEIL_OK, VEIL_VER = check_veil()
CHROME_PATH = check_chrome()

# ============================================
# УМНОЕ ОЖИДАНИЕ (АДАПТИРОВАНО ИЗ PYDoll)
# ============================================

class SmartWait:
    """Умное ожидание с несколькими стратегиями"""
    
    DEFAULT_TIMEOUT = 30  # секунд
    RETRY_INTERVAL = 0.5   # секунд
    
    @staticmethod
    async def wait_for_load(timeout: int = DEFAULT_TIMEOUT):
        """Ожидание document.readyState === 'complete'"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                state = js("document.readyState")
                if state == "complete":
                    logger.info(f"✅ Страница загружена (readyState: complete)")
                    return True
                await asyncio.sleep(SmartWait.RETRY_INTERVAL)
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при проверке readyState: {e}")
                await asyncio.sleep(SmartWait.RETRY_INTERVAL)
        
        logger.warning(f"⏰ Таймаут загрузки страницы ({timeout}с)")
        return False
    
    @staticmethod
    async def wait_for_network_idle(timeout: int = DEFAULT_TIMEOUT, idle_time: float = 1.0):
        """Ожидание завершения сетевой активности"""
        start = time.time()
        active_requests = 0
        
        while time.time() - start < timeout:
            try:
                # Получаем количество активных запросов через CDP
                result = cdp("Network.getActiveRequests")
                if result and result.get("count", 0) == 0:
                    # Проверяем, что запросов нет в течение idle_time
                    await asyncio.sleep(idle_time)
                    result = cdp("Network.getActiveRequests")
                    if result and result.get("count", 0) == 0:
                        logger.info(f"✅ Сеть проста ({idle_time}с без запросов)")
                        return True
                await asyncio.sleep(SmartWait.RETRY_INTERVAL)
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при проверке сети: {e}")
                await asyncio.sleep(SmartWait.RETRY_INTERVAL)
        
        logger.warning(f"⏰ Таймаут ожидания сети ({timeout}с)")
        return False
    
    @staticmethod
    async def wait_for_selector(selector: str, timeout: int = DEFAULT_TIMEOUT):
        """Ожидание появления элемента по CSS-селектору"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                exists = js(f"!!document.querySelector('{selector}')")
                if exists:
                    logger.info(f"✅ Элемент найден: {selector}")
                    return True
                await asyncio.sleep(SmartWait.RETRY_INTERVAL)
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при поиске {selector}: {e}")
                await asyncio.sleep(SmartWait.RETRY_INTERVAL)
        
        logger.warning(f"⏰ Таймаут ожидания элемента {selector} ({timeout}с)")
        return False
    
    @staticmethod
    async def wait_for_text(text: str, timeout: int = DEFAULT_TIMEOUT):
        """Ожидание появления текста на странице"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                body = js("document.body.innerText")
                if text in body:
                    logger.info(f"✅ Текст найден: {text[:50]}...")
                    return True
                await asyncio.sleep(SmartWait.RETRY_INTERVAL)
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при поиске текста: {e}")
                await asyncio.sleep(SmartWait.RETRY_INTERVAL)
        
        logger.warning(f"⏰ Таймаут ожидания текста ({timeout}с)")
        return False
    
    @staticmethod
    async def wait_for_condition(condition: str, timeout: int = DEFAULT_TIMEOUT):
        """Ожидание выполнения JavaScript условия"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                result = js(condition)
                if result:
                    logger.info(f"✅ Условие выполнено: {condition[:50]}...")
                    return True
                await asyncio.sleep(SmartWait.RETRY_INTERVAL)
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при проверке условия: {e}")
                await asyncio.sleep(SmartWait.RETRY_INTERVAL)
        
        logger.warning(f"⏰ Таймаут ожидания условия ({timeout}с)")
        return False
    
    @staticmethod
    async def wait_for_visible(selector: str, timeout: int = DEFAULT_TIMEOUT):
        """Ожидание видимости элемента"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                visible = js(f"""
                    (() => {{
                        const el = document.querySelector('{selector}');
                        if (!el) return false;
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    }})()
                """)
                if visible:
                    logger.info(f"✅ Элемент видим: {selector}")
                    return True
                await asyncio.sleep(SmartWait.RETRY_INTERVAL)
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при проверке видимости: {e}")
                await asyncio.sleep(SmartWait.RETRY_INTERVAL)
        
        logger.warning(f"⏰ Таймаут ожидания видимости {selector} ({timeout}с)")
        return False

class Retry:
    """Декоратор для повторных попыток"""
    
    def __init__(self, max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
        self.max_retries = max_retries
        self.delay = delay
        self.backoff = backoff
    
    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = self.delay
            
            for attempt in range(self.max_retries + 1):
                try:
                    if attempt > 0:
                        logger.info(f"🔄 Попытка {attempt}/{self.max_retries} для {func.__name__}")
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < self.max_retries:
                        wait_time = current_delay * (self.backoff ** attempt)
                        logger.warning(f"⚠️ Ошибка: {e}. Повтор через {wait_time:.2f}с")
                        await asyncio.sleep(wait_time)
            
            logger.error(f"❌ Все {self.max_retries} попыток провалились для {func.__name__}")
            raise last_exception
        return wrapper

# ============================================
# ПОМОЩНИКИ ДЛЯ РАБОТЫ С ACCESSIBILITY TREE
# ============================================

def get_ax_tree():
    try:
        result = cdp("Accessibility.getFullAXTree")
        return result.get("nodes", [])
    except Exception as e:
        logger.error(f"❌ Ошибка получения AX Tree: {e}")
        return []

def find_element_by_role(nodes, role, name=None):
    for node in nodes:
        if node.get("role") == role:
            if name is None or node.get("name") == name:
                return node
    return None

def get_element_coords(backend_node_id):
    try:
        result = cdp("DOM.getBoxModel", backendNodeId=backend_node_id)
        if result and "model" in result and "content" in result["model"]:
            box = result["model"]["content"]
            x = sum(box[0::2]) / 4
            y = sum(box[1::2]) / 4
            return x, y
    except Exception as e:
        logger.error(f"❌ Ошибка получения координат: {e}")
    return None, None

def click_element_by_role(role, name=None):
    nodes = get_ax_tree()
    target = find_element_by_role(nodes, role, name)
    if not target:
        logger.warning(f"⚠️ Элемент не найден: role={role}, name={name}")
        return False
    
    backend_id = target.get("backendDOMNodeId")
    if not backend_id:
        logger.warning("⚠️ Нет backendDOMNodeId")
        return False
    
    x, y = get_element_coords(backend_id)
    if x is None or y is None:
        return False
    
    click_at_xy(x, y)
    logger.info(f"✅ Клик по {role}:{name} at ({x:.0f}, {y:.0f})")
    return True

def get_text_from_ax_tree():
    nodes = get_ax_tree()
    result = []
    for node in nodes:
        role = node.get("role", "unknown")
        name = node.get("name", "")
        if name:
            result.append(f"[{role}] {name}")
    return "\n".join(result) if result else "Нет текста в AX Tree"

# ============================================
# УНИВЕРСАЛЬНАЯ ОЧИСТКА ВКЛАДОК
# ============================================

def cleanup_tabs(keep_one=True):
    try:
        tabs = list_tabs()
        if not tabs:
            logger.info("ℹ️ Нет открытых вкладок")
            return
        
        logger.info(f"🧹 Очистка: {len(tabs)} вкладок")
        
        if keep_one and len(tabs) > 1:
            for i, tab in enumerate(tabs):
                if i == 0:
                    continue
                try:
                    switch_tab(tab)
                    close_tab()
                    logger.info(f"✅ Закрыта вкладка: {tab}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось закрыть {tab}: {e}")
            
            try:
                switch_tab(tabs[0])
                goto_url("about:blank")
                wait_for_load()
                logger.info("✅ Оставлена одна чистая вкладка")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось переключиться: {e}")
        else:
            for tab in tabs:
                try:
                    switch_tab(tab)
                    close_tab()
                    logger.info(f"✅ Закрыта вкладка: {tab}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось закрыть {tab}: {e}")
            
            new_tab("about:blank")
            wait_for_load()
            logger.info("✅ Все вкладки закрыты, создана новая")
            
    except Exception as e:
        logger.error(f"❌ Ошибка очистки: {e}")

def set_cookies_via_js():
    try:
        new_tab("https://x.com")
        SmartWait.wait_for_load(timeout=30)
        
        js_code = """
        (function() {
            const cookies = %s;
            let success = 0;
            let failed = 0;
            let errors = [];
            
            cookies.forEach(function(cookie) {
                try {
                    let cookieString = cookie.name + '=' + cookie.value;
                    if (cookie.domain) cookieString += '; domain=' + cookie.domain;
                    if (cookie.path) cookieString += '; path=' + cookie.path;
                    if (cookie.secure) cookieString += '; secure';
                    if (cookie.sameSite && cookie.sameSite !== 'unspecified') {
                        cookieString += '; SameSite=' + cookie.sameSite;
                    }
                    document.cookie = cookieString;
                    success++;
                } catch(e) {
                    failed++;
                    errors.push(cookie.name + ': ' + e.message);
                }
            });
            
            return {
                success: success, 
                failed: failed, 
                errors: errors,
                total: cookies.length
            };
        })()
        """ % json.dumps(COOKIES)
        
        result = js(js_code)
        
        if result and result.get('success', 0) > 0:
            logger.info(f"✅ Установлено кук: {result.get('success')} из {result.get('total')}")
            if result.get('failed', 0) > 0:
                logger.warning(f"⚠️ Не удалось установить: {result.get('errors', [])}")
            return result.get('success', 0) > 0
        else:
            logger.error(f"❌ Не удалось установить куки: {result}")
            return False
        
    except Exception as e:
        logger.error(f"❌ Ошибка установки кук через JS: {e}")
        return False

# ============================================
# ЭМУЛЯЦИЯ ЧЕЛОВЕЧЕСКОГО ПОВЕДЕНИЯ (УЛУЧШЕННАЯ)
# ============================================

def random_delay(min_ms: int = 500, max_ms: int = 3000):
    """Случайная задержка для имитации человека"""
    delay = random.randint(min_ms, max_ms) / 1000
    time.sleep(delay)
    logger.info(f"⏱️ Задержка {delay:.2f}с")

async def async_random_delay(min_ms: int = 500, max_ms: int = 3000):
    """Асинхронная случайная задержка"""
    delay = random.randint(min_ms, max_ms) / 1000
    await asyncio.sleep(delay)
    logger.info(f"⏱️ Задержка {delay:.2f}с")

def bezier_curve(p0: tuple, p1: tuple, p2: tuple, t: float) -> tuple:
    """Кривая Безье для естественного движения мыши"""
    x = (1-t)**2 * p0[0] + 2*(1-t)*t * p1[0] + t**2 * p2[0]
    y = (1-t)**2 * p0[1] + 2*(1-t)*t * p1[1] + t**2 * p2[1]
    return (int(x), int(y))

def fitts_law_distance(distance: int, width: int = 50) -> float:
    """Закон Фиттса: время движения зависит от расстояния"""
    a, b = 100, 30  # ms
    return a + b * math.log2(distance / width + 1)

async def human_mouse_move(target_x: int, target_y: int, current_x: int = 0, current_y: int = 0):
    """Движение мыши по кривой Безье с физикой"""
    # 1. Контрольные точки для кривой
    dx, dy = target_x - current_x, target_y - current_y
    cp1_x = current_x + dx * random.uniform(0.2, 0.4)
    cp1_y = current_y + dy * random.uniform(0.2, 0.4) + random.randint(-50, 50)
    
    # 2. Расчёт времени по закону Фиттса
    distance = math.hypot(dx, dy)
    duration = fitts_law_distance(distance) / 1000  # в секундах
    
    # 3. Движение с колоколообразной скоростью
    steps = random.randint(20, 40)
    for i in range(steps + 1):
        t = i / steps
        # Колоколообразная скорость (minimum-jerk)
        velocity = math.sin(t * math.pi)
        t_adj = t * velocity  # Нелинейный прогресс
        
        x, y = bezier_curve((current_x, current_y), (cp1_x, cp1_y), (target_x, target_y), t_adj)
        
        # Тремор (гауссов шум)
        if random.random() < 0.3:
            x += random.gauss(0, 1)
            y += random.gauss(0, 1)
        
        await asyncio.sleep(duration / steps)
    
    # 4. Overshoot correction (70% шанс)
    if random.random() < 0.7 and distance > 100:
        overshoot = random.randint(int(distance * 0.03), int(distance * 0.12))
        # Промахнулись
        await asyncio.sleep(random.uniform(0.05, 0.15))
        # Скорректировались
        await asyncio.sleep(random.uniform(0.05, 0.15))

async def human_click(x: int, y: int):
    """Человеческий клик с физикой"""
    # 1. Движение к цели
    await human_mouse_move(x, y)
    
    # 2. Микро-пауза перед кликом
    await asyncio.sleep(random.uniform(0.05, 0.2))
    
    # 3. Нажатие с микро-дрожанием
    cdp("Input.dispatchMouseEvent", {
        "type": "mousePressed",
        "x": x + random.randint(-2, 2),
        "y": y + random.randint(-2, 2),
        "button": "left",
        "clickCount": 1
    })
    
    await asyncio.sleep(random.uniform(0.05, 0.15))
    
    cdp("Input.dispatchMouseEvent", {
        "type": "mouseReleased",
        "x": x + random.randint(-2, 2),
        "y": y + random.randint(-2, 2),
        "button": "left",
        "clickCount": 1
    })
    
    logger.info(f"🖱️ Человеческий клик по ({x}, {y})")

async def human_scroll(dy: int = 100, steps: int = None):
    """Человеческая прокрутка с переменной скоростью"""
    if steps is None:
        steps = random.randint(5, 10)
    
    per_step = dy / steps
    
    for i in range(steps):
        # Разная скорость на каждом шаге
        step_dy = per_step * random.uniform(0.5, 1.5)
        cdp("Input.dispatchMouseEvent", {
            "type": "mouseWheel",
            "deltaX": random.randint(-5, 5),
            "deltaY": step_dy
        })
        await asyncio.sleep(random.uniform(0.03, 0.1))
    
    logger.info(f"📜 Человеческая прокрутка на {dy}px")

async def human_type_text(text: str):
    """Ввод текста с переменной скоростью и опечатками"""
    for char in text:
        # Переменная скорость ввода (50-200ms на символ)
        delay = random.uniform(0.05, 0.2)
        await asyncio.sleep(delay)
        
        # 2% шанс опечатки
        if random.random() < 0.02 and len(text) > 3:
            # Ошибка
            error_char = random.choice('qwertyuiopasdfghjklzxcvbnm')
            await js(f"document.activeElement.value += '{error_char}'")
            await asyncio.sleep(random.uniform(0.2, 0.4))
            # Backspace
            await js("document.activeElement.value = document.activeElement.value.slice(0, -1)")
            await asyncio.sleep(random.uniform(0.1, 0.2))
        
        # Вводим правильный символ
        await js(f"document.activeElement.value += '{char}'")

# ============================================
# УМНЫЙ ГОТУ (АДАПТИРОВАН ИЗ PYDoll)
# ============================================

class SmartGo:
    """Умная навигация с ожиданием"""
    
    @staticmethod
    @Retry(max_retries=3, delay=1.0)
    async def go_to(url: str, timeout: int = 30, wait_network: bool = True):
        """Умный переход с ожиданием загрузки"""
        logger.info(f"🌐 Переход на {url}")
        
        # 1. Переходим
        goto_url(url)
        
        # 2. Ждём загрузку DOM
        await SmartWait.wait_for_load(timeout=timeout)
        
        # 3. Ждём сеть, если нужно
        if wait_network:
            await SmartWait.wait_for_network_idle(timeout=timeout)
        
        # 4. Случайная пауза (имитация человека)
        await async_random_delay(1000, 3000)
        
        logger.info(f"✅ Страница загружена: {url}")
        return True
    
    @staticmethod
    @Retry(max_retries=3, delay=1.0)
    async def click_selector(selector: str, timeout: int = 30):
        """Умный клик с ожиданием видимости"""
        # 1. Ждём появления элемента
        await SmartWait.wait_for_selector(selector, timeout=timeout)
        
        # 2. Ждём видимости
        await SmartWait.wait_for_visible(selector, timeout=timeout)
        
        # 3. Получаем координаты
        result = js(f"""
            (() => {{
                const el = document.querySelector('{selector}');
                const rect = el.getBoundingClientRect();
                return {{
                    x: rect.left + rect.width/2,
                    y: rect.top + rect.height/2
                }};
            }})()
        """)
        
        # 4. Человеческий клик
        await human_click(int(result['x']), int(result['y']))
        
        # 5. Ждём реакции страницы
        await async_random_delay(500, 1500)
        
        logger.info(f"✅ Клик по {selector}")
        return True

# ============================================
# DSPy ИНТЕГРАЦИЯ
# ============================================

try:
    import warnings
    import httpx
    import dspy
    from dspy import Signature, InputField, OutputField, Module, settings, ReActV2, Tool
    warnings.filterwarnings("ignore")
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False
    logger.warning("⚠️ DSPy не установлен. Установи: pip install dspy httpx")

class AgnesLM(dspy.LM):
    def __init__(self, model="agnes-2.0-flash", api_key=None, **kwargs):
        self.api_key = api_key or os.environ.get("AGNES_API_KEY")
        self.model = model
        
        super().__init__(
            model=model, 
            model_type="chat",
            temperature=kwargs.get("temperature", 0.3),
            max_tokens=kwargs.get("max_tokens", 2000),
            cache=False
        )
        
        self.provider = "agnes-ai"
        self.forward_contract = "legacy"
    
    def forward(self, prompt=None, messages=None, **kwargs):
        if not self.api_key:
            return ["Ошибка: API ключ не задан"]
        
        params = {**self.kwargs, **kwargs}
        
        if messages:
            api_messages = messages
        else:
            api_messages = [{"role": "user", "content": prompt or ""}]
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature": params.get("temperature", 0.3),
            "max_tokens": params.get("max_tokens", 2000)
        }
        
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    "https://apihub.agnes-ai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                
                if "choices" in data and len(data["choices"]) > 0:
                    result = data["choices"][0]["message"]["content"]
                    return [result]
                return ["Ошибка: пустой ответ от API"]
                
        except Exception as e:
            logger.error(f"❌ Ошибка Agnes API: {e}")
            return [f"Ошибка: {str(e)}"]
    
    def __call__(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)
    
    async def aforward(self, prompt=None, messages=None, **kwargs):
        return self.forward(prompt=prompt, messages=messages, **kwargs)


class BrowserTask(Signature):
    question = InputField(desc="Задача пользователя")
    answer = OutputField(desc="Ответ с использованием Browser Harness")


def create_browser_agent(tools, max_iters=10):
    try:
        agent = ReActV2(
            signature=BrowserTask,
            tools=tools,
            max_iters=max_iters,
        )
        logger.info("✅ ReActV2 агент создан")
        return agent
    except Exception as e:
        logger.error(f"❌ Ошибка создания агента: {e}")
        return None


def init_dspy(api_key=None, tools=None, max_iters=10):
    api_key = api_key or os.environ.get("AGNES_API_KEY")
    
    if not api_key:
        logger.warning("⚠️ AGNES_API_KEY не задан, DSPy не инициализирован")
        return None, None
    
    try:
        lm = AgnesLM(
            api_key=api_key,
            temperature=0.3,
            max_tokens=2000
        )
        
        settings.configure(lm=lm)
        logger.info("✅ DSPy настроен с AgnesLM")
        
        if tools:
            agent = create_browser_agent(tools, max_iters)
        else:
            agent = None
        
        return lm, agent
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации DSPy: {e}")
        return None, None


def run_agent(agent, question: str) -> str:
    if not agent:
        return "❌ Агент не инициализирован"
    
    try:
        result = agent(question=question)
        answer = getattr(result, 'answer', str(result))
        return answer if answer and answer.strip() else "❌ Агент вернул пустой ответ"
    except Exception as e:
        logger.error(f"❌ Ошибка выполнения агента: {e}")
        return f"❌ Ошибка: {str(e)}"

# ============================================
# БРАУЗЕР
# ============================================

browser_instance = None
chrome_process = None
cdp_url = "http://127.0.0.1:9222"
dspy_agent = None
dspy_lm = None

# ============================================
# DSPy ЛОГИРОВАНИЕ В ФАЙЛ
# ============================================

def save_dspy_log(question: str, answer: str, history: str = "", llm_history: str = "", username: str = "unknown"):
    try:
        log_file = "dspy.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("=" * 60 + "\n")
            f.write(f"📅 Время: {timestamp}\n")
            f.write(f"👤 Пользователь: {username}\n")
            f.write(f"❓ Вопрос: {question}\n\n")
            
            f.write("=" * 60 + "\n")
            f.write("📋 **ТРАЕКТОРИЯ ШАГОВ**\n")
            f.write("=" * 60 + "\n\n")
            f.write(history if history else "Нет истории шагов\n")
            f.write("\n")
            
            f.write("=" * 60 + "\n")
            f.write("🧠 **LLM ВЫЗОВЫ**\n")
            f.write("=" * 60 + "\n\n")
            f.write(llm_history if llm_history else "Нет LLM вызовов\n")
            f.write("\n")
            
            f.write("=" * 60 + "\n")
            f.write(f"✅ **ОТВЕТ:**\n{answer}\n")
            f.write("=" * 60 + "\n\n")
        
        logger.info(f"✅ Полный лог сохранён в {log_file}")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения лога: {e}")

# ============================================
# ИНИЦИАЛИЗАЦИЯ DSPy С ИНСТРУМЕНТАМИ
# ============================================

def init_dspy_agent():
    global dspy_agent, dspy_lm
    
    if not DSPY_AVAILABLE:
        logger.warning("⚠️ DSPy не доступен")
        return
    
    AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
    if not AGNES_API_KEY:
        logger.warning("⚠️ AGNES_API_KEY не задан, DSPy отключен")
        return
    
    try:
        def tool_new_tab(url: str = "https://example.com") -> str:
            try:
                new_tab(url)
                SmartWait.wait_for_load(timeout=30)
                random_delay(1000, 3000)
                return f"✅ Открыта вкладка: {url}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_goto_url(url: str) -> str:
            try:
                SmartGo.go_to(url, timeout=30)
                return f"✅ Перешел на {url}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_wait_for_load() -> str:
            try:
                SmartWait.wait_for_load(timeout=30)
                random_delay(500, 2000)
                return "✅ Страница загружена"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_ensure_real_tab() -> str:
            try:
                ensure_real_tab()
                return "✅ Вкладка восстановлена"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_get_ax_tree() -> str:
            try:
                nodes = get_ax_tree()
                if not nodes:
                    return "❌ AX Tree пуст"
                result = []
                for node in nodes[:50]:
                    role = node.get("role", "unknown")
                    name = node.get("name", "")
                    if name:
                        result.append(f"[{role}] {name}")
                return "\n".join(result) if result else "Нет текста в AX Tree"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_click_by_role(role: str, name: str = None) -> str:
            try:
                nodes = get_ax_tree()
                target = find_element_by_role(nodes, role, name)
                if not target:
                    return f"❌ Элемент не найден: {role}: {name or 'без имени'}"
                backend_id = target.get("backendDOMNodeId")
                if not backend_id:
                    return "❌ Нет backendDOMNodeId"
                x, y = get_element_coords(backend_id)
                if x is None or y is None:
                    return "❌ Не удалось получить координаты"
                asyncio.run(human_click(int(x), int(y)))
                random_delay(500, 1500)
                return f"✅ Человеческий клик по {role}: {name or 'без имени'}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_click_by_coords(x: int, y: int) -> str:
            try:
                asyncio.run(human_click(x, y))
                random_delay(500, 1500)
                return f"✅ Человеческий клик по ({x}, {y})"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_get_coords_by_role(role: str, name: str = None) -> str:
            try:
                nodes = get_ax_tree()
                target = find_element_by_role(nodes, role, name)
                if not target:
                    return f"❌ Элемент не найден: {role}: {name or 'без имени'}"
                backend_id = target.get("backendDOMNodeId")
                if not backend_id:
                    return "❌ Нет backendDOMNodeId"
                x, y = get_element_coords(backend_id)
                if x is None or y is None:
                    return "❌ Не удалось получить координаты"
                return f"Координаты: ({x:.0f}, {y:.0f})"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_page_info() -> str:
            try:
                info = page_info()
                return f"URL: {info.get('url', 'unknown')}\nTitle: {info.get('title', 'unknown')}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_capture_screenshot(filename: str = None) -> str:
            try:
                if not filename:
                    timestamp = int(time.time())
                    filename = f"screenshot_{timestamp}.png"
                path = capture_screenshot(filename)
                random_delay(500, 1500)
                return f"✅ Скриншот сохранен: {path}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_js(expression: str) -> str:
            try:
                result = js(expression)
                return str(result) if result is not None else "✅ JS выполнен"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_fill_input(selector: str, text: str) -> str:
            try:
                fill_input(selector, text)
                random_delay(500, 1500)
                return f"✅ Заполнено: {selector}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_scroll(dx: int, dy: int) -> str:
            try:
                asyncio.run(human_scroll(dy))
                random_delay(500, 1500)
                return f"✅ Человеческая прокрутка на ({dx}, {dy})"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_human_type(text: str) -> str:
            try:
                asyncio.run(human_type_text(text))
                random_delay(500, 1500)
                return f"✅ Человеческий ввод: {text[:20]}..."
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_list_tabs() -> str:
            try:
                tabs = list_tabs()
                return f"Вкладки: {tabs}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_current_tab() -> str:
            try:
                tab = current_tab()
                return f"Текущая вкладка: {tab}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_switch_tab(tab_id: int) -> str:
            try:
                switch_tab(tab_id)
                return f"✅ Переключился на вкладку {tab_id}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_close_tab() -> str:
            try:
                close_tab()
                return "✅ Вкладка закрыта"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        def tool_set_x_cookies() -> str:
            try:
                success = set_cookies_via_js()
                if success:
                    return "✅ Куки X.com установлены"
                return "❌ Ошибка установки кук"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        
        tools = [
            Tool(tool_new_tab),
            Tool(tool_goto_url),
            Tool(tool_wait_for_load),
            Tool(tool_ensure_real_tab),
            Tool(tool_get_ax_tree),
            Tool(tool_click_by_role),
            Tool(tool_click_by_coords),
            Tool(tool_get_coords_by_role),
            Tool(tool_page_info),
            Tool(tool_capture_screenshot),
            Tool(tool_js),
            Tool(tool_fill_input),
            Tool(tool_scroll),
            Tool(tool_human_type),
            Tool(tool_list_tabs),
            Tool(tool_current_tab),
            Tool(tool_switch_tab),
            Tool(tool_close_tab),
            Tool(tool_set_x_cookies),
        ]
        
        dspy_lm, dspy_agent = init_dspy(
            api_key=AGNES_API_KEY,
            tools=tools,
            max_iters=15
        )
        
        if dspy_agent:
            logger.info(f"✅ DSPy агент инициализирован с {len(tools)} инструментами")
        else:
            logger.warning("⚠️ Не удалось создать DSPy агента")
            
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации DSPy: {e}")
        dspy_agent = None

# ============================================
# TELEGRAM КОМАНДЫ
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ **Veil + browser-harness + X.com**\n\n"
        "Команды:\n"
        "/start_veil - запустить Veil с куками X.com\n"
        "/check - проверить маскировку\n"
        "/checkxcom - проверить авторизацию на X.com\n"
        "/screen <url> - сделать скриншот страницы\n"
        "/harness - тест harness\n"
        "/ax - показать Accessibility Tree\n"
        "/dspy <задача> - задать вопрос агенту\n"
        "/dspy_log - скачать лог DSPy\n"
        "/diag - диагностика"
    )

async def ax_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌳 Получаю Accessibility Tree...")
    
    if not browser_instance:
        await update.message.reply_text("❌ Сначала запусти Veil: /start_veil")
        return
    
    try:
        text = get_text_from_ax_tree()
        if text and len(text) > 4000:
            text = text[:4000] + "\n\n... (обрезано)"
        await update.message.reply_text(
            f"🌳 **Accessibility Tree**\n\n{text}"
        )
        
        cleanup_tabs(keep_one=True)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def start_veil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_instance, chrome_process
    await update.message.reply_text("🔄 Запускаю Veil...")
    
    if not VEIL_OK:
        await update.message.reply_text("❌ Veil не установлен!")
        return
    
    try:
        if not CHROME_PATH:
            await update.message.reply_text("❌ Chrome не найден!")
            return
        
        await update.message.reply_text("🔄 Запускаю Chrome с маскировкой...")
        
        chrome_process = subprocess.Popen(
            [
                CHROME_PATH,
                "--headless=new",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--remote-debugging-port=9222",
                "--use-gl=angle",
                "--use-angle=gl-egl",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-features=BlockInsecurePrivateNetworkRequests",
                "--disable-component-extensions-with-background-pages",
                "--disable-default-apps",
                "--disable-extensions",
                "--disable-plugins",
                "--disable-translate",
                "--disable-sync",
                "--disable-background-networking",
                "--disable-client-side-phishing-detection",
                "--disable-hang-monitor",
                "--disable-prompt-on-repost",
                "--disable-speech-api",
                "--disable-voice-input",
                "--disable-print-preview",
                "--disable-bundled-ppapi-flash",
                "--disable-setuid-sandbox",
                f"--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        await asyncio.sleep(2)
        
        os.environ["BU_CDP_URL"] = cdp_url
        ensure_daemon()
        logger.info("✅ Daemon browser-harness запущен")
        
        from veilbrowser import Browser
        browser_instance = await Browser.connect(cdp_url)
        
        await update.message.reply_text("🍪 Устанавливаю куки X.com...")
        success = set_cookies_via_js()
        if success:
            await update.message.reply_text(f"✅ Установлены куки X.com!")
        else:
            await update.message.reply_text("⚠️ Не удалось установить куки")
        
        if DSPY_AVAILABLE:
            await update.message.reply_text("🧠 Инициализирую DSPy агента...")
            init_dspy_agent()
        
        new_tab("https://x.com")
        SmartWait.wait_for_load(timeout=30)
        random_delay(2000, 5000)
        
        await update.message.reply_text(
            f"✅ **Veil запущен!**\n\n"
            f"🔌 CDP: {cdp_url}\n"
            f"🆔 PID: {chrome_process.pid}\n"
            f"🍪 Куки X.com: {'✅' if success else '❌'}\n"
            f"🧠 DSPy: {'✅ Активен' if dspy_agent else '❌ Отключен'}\n"
            f"👤 Эмуляция человека: ✅\n"
            f"⏰ Умное ожидание: ✅\n\n"
            f"📋 Команды:\n"
            f"/checkxcom - проверить авторизацию на X.com\n"
            f"/screen <url> - сделать скриншот\n"
            f"/ax - показать Accessibility Tree\n"
            f"/dspy <задача> - AI-агент\n"
            f"/dspy_log - скачать лог DSPy"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def check_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Проверяю браузер...")
    
    if not browser_instance:
        await update.message.reply_text("❌ Сначала запусти Veil: /start_veil")
        return
    
    try:
        new_tab("https://bot.sannysoft.com")
        SmartWait.wait_for_load(timeout=30)
        random_delay(1000, 3000)
        
        screenshot_path = capture_screenshot()
        if screenshot_path and os.path.exists(screenshot_path):
            with open(screenshot_path, 'rb') as f:
                await update.message.reply_photo(photo=f, caption="📸 Проверка маскировки")
        
        result = js("""
            () => ({
                webdriver: navigator.webdriver,
                userAgent: navigator.userAgent,
                platform: navigator.platform
            })
        """)
        
        webdriver = result.get('webdriver')
        if webdriver in (False, None):
            verdict = "✅ **Браузер НЕОТЛИЧИМ!** 🎉"
        else:
            verdict = "⚠️ **Браузер как бот**"
        
        await update.message.reply_text(
            f"🔍 **Результат**\n\n"
            f"{verdict}\n"
            f"• webdriver: `{webdriver}`\n"
            f"• platform: `{result.get('platform')}`\n\n"
            f"💡 `None` или `false` — идеально!"
        )
        
        close_tab()
        cleanup_tabs(keep_one=True)
        random_delay(1000, 3000)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def check_xcom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Проверяю X.com...")
    
    if not browser_instance:
        await update.message.reply_text("❌ Сначала запусти Veil: /start_veil")
        return
    
    try:
        new_tab("https://x.com")
        SmartWait.wait_for_load(timeout=30)
        random_delay(2000, 5000)
        
        screenshot_path = capture_screenshot()
        if screenshot_path and os.path.exists(screenshot_path):
            with open(screenshot_path, 'rb') as f:
                await update.message.reply_photo(photo=f, caption="📸 X.com после загрузки")
        
        result = js("""
            () => {
                const signUp = document.querySelector('[data-testid="signUpButton"]');
                const logIn = document.querySelector('[data-testid="loginButton"]');
                const profile = document.querySelector('[data-testid="AppTabBar_Profile_Link"]');
                const home = document.querySelector('[data-testid="AppTabBar_Home_Link"]');
                const hasAuth = document.cookie.includes('auth_token');
                const hasTwid = document.cookie.includes('twid');
                
                return {
                    hasAuthToken: hasAuth,
                    hasTwid: hasTwid,
                    hasSignUp: !!signUp,
                    hasLogIn: !!logIn,
                    hasProfile: !!profile,
                    hasHome: !!home,
                    title: document.title,
                    url: window.location.href
                };
            }
        """)
        
        report = "🔍 **Проверка X.com**\n\n"
        report += "🍪 **Куки:**\n"
        report += f"• auth_token: {'✅' if result.get('hasAuthToken') else '❌'}\n"
        report += f"• twid: {'✅' if result.get('hasTwid') else '❌'}\n\n"
        report += "🖥️ **UI элементы:**\n"
        report += f"• Кнопка 'Sign up': {'❌' if result.get('hasSignUp') else '✅ (скрыта)'}\n"
        report += f"• Кнопка 'Log in': {'❌' if result.get('hasLogIn') else '✅ (скрыта)'}\n"
        report += f"• Профиль: {'✅' if result.get('hasProfile') else '❌'}\n"
        report += f"• Домой: {'✅' if result.get('hasHome') else '❌'}\n\n"
        
        if result.get('hasProfile') or result.get('hasHome'):
            report += "✅ **АВТОРИЗОВАН!**\n"
        elif result.get('hasSignUp') or result.get('hasLogIn'):
            report += "⚠️ **НЕ АВТОРИЗОВАН!**\n"
        else:
            report += "❓ **НЕИЗВЕСТНО**\n"
        
        await update.message.reply_text(report)
        
        close_tab()
        cleanup_tabs(keep_one=True)
        random_delay(1000, 3000)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def screen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ **Укажи URL!**\n\n"
            "Пример: `/screen https://example.com`",
            parse_mode='Markdown'
        )
        return
    
    url = context.args[0]
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    await update.message.reply_text(f"🔄 Открываю `{url}` и делаю скриншот...", parse_mode='Markdown')
    
    if not browser_instance:
        await update.message.reply_text("❌ Сначала запусти Veil: /start_veil")
        return
    
    try:
        new_tab(url)
        SmartWait.wait_for_load(timeout=30)
        random_delay(1000, 3000)
        
        timestamp = int(time.time())
        filename = f"screenshot_{timestamp}.png"
        screenshot_path = capture_screenshot(filename)
        
        if screenshot_path and os.path.exists(screenshot_path):
            with open(screenshot_path, 'rb') as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=f"📸 **Скриншот:** `{url}`"
                )
            
            info = page_info()
            await update.message.reply_text(
                f"✅ **Готово!**\n\n"
                f"📌 **Title:** {info.get('title', 'N/A')[:100]}\n"
                f"🔗 **URL:** {info.get('url', url)}"
            )
        else:
            await update.message.reply_text("❌ Не удалось сохранить скриншот")
        
        close_tab()
        cleanup_tabs(keep_one=True)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def test_harness(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧪 Тестирую browser-harness...")
    
    if not browser_instance:
        await update.message.reply_text("❌ Сначала запусти Veil: /start_veil")
        return
    
    try:
        report = "🧪 **Тест browser-harness (по документации)**\n\n"
        
        new_tab("https://example.com")
        SmartWait.wait_for_load(timeout=30)
        random_delay(1000, 3000)
        report += "✅ new_tab()\n"
        
        ax = get_text_from_ax_tree()
        report += f"✅ AX Tree: {len(ax)} символов\n"
        
        nodes = get_ax_tree()
        link = find_element_by_role(nodes, "link", "More information...")
        if link:
            x, y = get_element_coords(link.get("backendDOMNodeId"))
            await human_click(int(x), int(y))
            random_delay(1000, 3000)
            report += f"✅ Человеческий клик по ссылке 'More information...'\n"
        else:
            report += "ℹ️ Ссылка 'More information...' не найдена\n"
        
        screenshot_path = capture_screenshot()
        if screenshot_path and os.path.exists(screenshot_path):
            with open(screenshot_path, 'rb') as f:
                await update.message.reply_photo(photo=f, caption="📸 После клика")
            report += "✅ capture_screenshot()\n"
        
        close_tab()
        cleanup_tabs(keep_one=True)
        
        await update.message.reply_text(report + "\n🎉 Все функции работают по документации!")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def dspy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🧠 **DSPy Agent (по документации browser-harness)**\n\n"
            "Доступные инструменты:\n"
            "• tool_new_tab / tool_goto_url\n"
            "• tool_get_ax_tree - Accessibility Tree (РЕКОМЕНДУЕТСЯ)\n"
            "• tool_click_by_role / tool_click_by_coords\n"
            "• tool_capture_screenshot - для проверки\n"
            "• tool_human_type - ввод с эмуляцией человека\n"
            "• tool_set_x_cookies - установить куки X.com\n\n"
            "Примеры:\n"
            "/dspy открой x.com и покажи заголовок\n"
            "/dspy установи куки X.com и открой страницу\n\n"
            "📊 Полная траектория сохраняется в dspy.log"
        )
        return
    
    if not browser_instance:
        await update.message.reply_text("❌ Сначала запусти Veil: /start_veil")
        return
    
    if not DSPY_AVAILABLE:
        await update.message.reply_text("❌ DSPy не установлен!\nУстанови: pip install dspy httpx")
        return
    
    if not dspy_agent:
        await update.message.reply_text(
            "❌ DSPy агент не инициализирован!\n\n"
            "Проверьте:\n"
            "1. Переменную AGNES_API_KEY\n"
            "2. Перезапустите /start_veil"
        )
        return
    
    user_query = " ".join(context.args)
    username = update.effective_user.username or "unknown"
    logger.info(f"👤 {username} DSPy запрос: {user_query}")
    
    status_msg = await update.message.reply_text("🧠 Думаю...")
    
    try:
        loop = asyncio.get_running_loop()
        
        f = io.StringIO()
        with redirect_stdout(f):
            answer = await loop.run_in_executor(None, run_agent, dspy_agent, user_query)
        
        history_output = f.getvalue()
        
        f_history = io.StringIO()
        with redirect_stdout(f_history):
            dspy.inspect_history(n=10)
        
        full_history = f_history.getvalue()
        
        if not answer or answer.strip() == "":
            await status_msg.edit_text("❌ Агент вернул пустой ответ")
            return
        
        save_dspy_log(user_query, answer, history_output, full_history, username)
        
        if len(answer) > 4000:
            answer = answer[:4000] + "\n\n... (обрезано)"
        
        await status_msg.edit_text(f"✅ **Результат:**\n\n{answer}")
        
        cleanup_tabs(keep_one=True)
        
    except Exception as e:
        logger.error(f"❌ DSPy ошибка: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:300]}")
        cleanup_tabs(keep_one=True)

async def dspy_log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_file = "dspy.log"
    
    if not os.path.exists(log_file):
        await update.message.reply_text("📄 **Лог DSPy пуст**\n\nПока нет записей. Используй /dspy чтобы начать.")
        return
    
    try:
        await update.message.reply_document(
            document=open(log_file, "rb"),
            filename="dspy.log",
            caption="📄 **Лог DSPy** (полная траектория выполнения)"
        )
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = f"📊 **Диагностика**\n\n"
    report += f"• Veil: {'✅' if VEIL_OK else '❌'} {VEIL_VER or ''}\n"
    report += f"• Chrome: {'✅' if CHROME_PATH else '❌'}\n"
    report += f"• Harness path: {'✅' if os.path.exists('browser-harness/src') else '❌'}\n"
    report += f"• Браузер: {'✅' if browser_instance else '❌'}\n"
    report += f"• DSPy: {'✅' if dspy_agent else '❌'}\n"
    report += f"• BU_CDP_URL: {os.environ.get('BU_CDP_URL', '❌')}\n"
    report += f"• AGNES_API_KEY: {'✅' if os.environ.get('AGNES_API_KEY') else '❌'}\n"
    report += f"• Куки X.com: {'✅' if COOKIES else '❌'} ({len(COOKIES)} шт.)\n"
    report += f"• DSPy лог: {'✅' if os.path.exists('dspy.log') else '❌'}\n"
    report += f"• Эмуляция человека: {'✅' if DSPY_AVAILABLE else '❌'}\n"
    report += f"• Умное ожидание: ✅\n"
    
    if CHROME_PATH:
        report += f"• Путь Chrome: `{CHROME_PATH}`\n"
    if chrome_process:
        report += f"• PID Chrome: `{chrome_process.pid}`\n"
    
    try:
        import requests
        response = requests.get("http://127.0.0.1:9222/json/version", timeout=2)
        if response.status_code == 200:
            report += f"• CDP: ✅ Доступен\n"
        else:
            report += f"• CDP: ⚠️ {response.status_code}\n"
    except:
        report += "• CDP: ❌ Не доступен\n"
    
    await update.message.reply_text(report)

# ============================================
# ЗАПУСК
# ============================================

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("start_veil", start_veil))
    app.add_handler(CommandHandler("check", check_browser))
    app.add_handler(CommandHandler("checkxcom", check_xcom))
    app.add_handler(CommandHandler("screen", screen_command))
    app.add_handler(CommandHandler("harness", test_harness))
    app.add_handler(CommandHandler("ax", ax_command))
    app.add_handler(CommandHandler("dspy", dspy_command))
    app.add_handler(CommandHandler("dspy_log", dspy_log_command))
    app.add_handler(CommandHandler("diag", diag))
    
    logger.info("🤖 Бот запущен (по документации browser-harness)!")
    logger.info("📋 Команды: /start_veil, /check, /checkxcom, /screen, /harness, /ax, /dspy, /dspy_log, /diag")
    logger.info(f"🍪 Загружено {len(COOKIES)} кук X.com")
    logger.info("👤 Эмуляция человека: включена")
    logger.info("⏰ Умное ожидание: включено")
    app.run_polling()

if __name__ == "__main__":
    main()