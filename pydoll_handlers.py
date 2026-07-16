import asyncio
import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.constants import PageLoadState, Key
from pydoll.decorators import retry
from pydoll.exceptions import ElementNotFound, WaitElementTimeout, NetworkError
from pydoll.extractor import ExtractionModel, Field
from pydoll.protocol.fetch.events import FetchEvent, RequestPausedEvent
from pydoll.protocol.network.types import ErrorReason

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# ============================================================
# 1. НАСТРОЙКА БРАУЗЕРА (ChromiumOptions) - полная версия
# ============================================================

def get_optimized_options(user_data_dir: Optional[str] = None) -> ChromiumOptions:
    """
    Полностью настроенный ChromiumOptions для Railway
    с явным указанием пути к Google Chrome
    """
    options = ChromiumOptions()
    
    # === ЯВНЫЙ ПУТЬ К БРАУЗЕРУ ===
    options.binary_location = "/usr/bin/google-chrome"  # Твой путь
    
    # === КРИТИЧЕСКИ ВАЖНО ДЛЯ RAILWAY ===
    options.headless = True
    options.add_argument('--headless=new')  # Новый headless-режим
    options.start_timeout = 15
    options.page_load_state = PageLoadState.INTERACTIVE  # Только DOM
    
    # === PERSISTENT CONTEXT (сохранение сессии) ===
    if user_data_dir:
        options.add_argument(f'--user-data-dir={user_data_dir}')
    
    # === ПРОИЗВОДИТЕЛЬНОСТЬ ===
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--disable-dev-shm-usage')  # Фикс для Docker
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-background-networking')
    options.add_argument('--disable-background-timer-throttling')
    options.add_argument('--disable-renderer-backgrounding')
    options.add_argument('--disable-sync')
    options.add_argument('--disable-translate')
    options.add_argument('--disable-features=NetworkPrediction')
    options.add_argument('--dns-prefetch-disable')
    options.add_argument('--disable-animations')
    
    # === СТЕЛС-РЕЖИМ (обход антибот-систем) ===
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    options.add_argument('--use-gl=swiftshader')
    options.add_argument('--force-webrtc-ip-handling-policy=disable_non_proxied_udp')
    options.add_argument('--lang=en-US')
    options.add_argument('--accept-lang=en-US,en;q=0.9')
    options.add_argument('--tz=America/New_York')
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    options.add_argument('--disable-reading-from-canvas')
    options.add_argument('--disable-features=AudioServiceOutOfProcess')
    
    # === БЕЗОПАСНОСТЬ (только для доверенной среды) ===
    options.add_argument('--no-sandbox')  # Нужен в Docker
    options.add_argument('--disable-setuid-sandbox')
    
    # === ОТОБРАЖЕНИЕ ===
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--force-device-scale-factor=1')
    
    # === ПРЕДПОЧТЕНИЯ БРАУЗЕРА ===
    options.browser_preferences = {
        'profile': {
            'default_content_setting_values': {
                'notifications': 2,
                'geolocation': 2,
            },
            'password_manager_enabled': False
        },
        'intl': {
            'accept_languages': 'en-US,en',
        },
        'browser': {
            'check_default_browser': False,
        }
    }
    
    # === ЗАЩИТА ОТ WEBRTC УТЕЧЕК ===
    options.webrtc_leak_protection = True
    
    return options


# ============================================================
# 2. БАЗОВЫЕ ФУНКЦИИ
# ============================================================

@retry(
    max_retries=3,
    exceptions=[ElementNotFound, WaitElementTimeout, NetworkError],
    delay=1.0,
    exponential_backoff=True
)
async def search_and_screenshot(query: str) -> str:
    """Поиск в Google со скриншотом"""
    screenshot_path = SCREENSHOTS_DIR / f"{query[:20].replace(' ', '_')}.png"
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.go_to('https://www.google.com')
        search_box = await tab.find(tag_name='textarea', name='q')
        await search_box.type_text(query, humanize=True)
        await tab.keyboard.press(Key.ENTER)
        await asyncio.sleep(3)
        await tab.screenshot(str(screenshot_path))
        return str(screenshot_path)


@retry(max_retries=2, exceptions=[NetworkError], delay=1.0)
async def get_page_title(url: str) -> str:
    """Получает заголовок страницы"""
    options = get_optimized_options()
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.go_to(url)
        return await tab.title


async def execute_javascript(url: str, script: str) -> str:
    """Выполняет JavaScript на странице"""
    options = get_optimized_options()
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.go_to(url)
        return str(await tab.execute_script(script))


async def take_screenshot_of_element(url: str, selector: str) -> str:
    """Делает скриншот элемента по CSS-селектору"""
    screenshot_path = SCREENSHOTS_DIR / f"element_{abs(hash(selector))}.png"
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.go_to(url)
        element = await tab.find(css_selector=selector)
        await element.screenshot(str(screenshot_path))
        return str(screenshot_path)


# ============================================================
# 3. SHADOW DOM
# ============================================================

async def find_in_shadow_dom(url: str, host_selector: str, inner_selector: str) -> str:
    """
    Находит элемент внутри Shadow DOM (включая закрытые shadow roots)
    """
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.go_to(url)
        
        host = await tab.find(css_selector=host_selector)
        shadow = await host.get_shadow_root()
        element = await shadow.query(css_selector=inner_selector)
        
        return await element.text


async def find_all_shadow_roots(url: str) -> List[str]:
    """
    Находит все shadow roots на странице
    """
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.go_to(url)
        
        shadow_roots = await tab.find_shadow_roots()
        
        results = []
        for sr in shadow_roots:
            checkbox = await sr.query('input[type="checkbox"]', raise_exc=False)
            if checkbox:
                results.append("Found checkbox in shadow root")
        
        return results


# ============================================================
# 4. NETWORK INTERCEPTION
# ============================================================

async def load_page_without_images(url: str) -> str:
    """
    Загружает страницу, блокируя все изображения и стили
    """
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        
        async def block_resource(event: RequestPausedEvent):
            request_id = event['params']['requestId']
            resource_type = event['params']['resourceType']
            
            if resource_type in ['Image', 'Stylesheet']:
                await tab.fail_request(request_id, ErrorReason.BLOCKED_BY_CLIENT)
            else:
                await tab.continue_request(request_id)
        
        await tab.enable_fetch_events()
        await tab.on(FetchEvent.REQUEST_PAUSED, block_resource)
        
        await tab.go_to(url)
        await asyncio.sleep(3)
        
        await tab.disable_fetch_events()
        
        screenshot_path = SCREENSHOTS_DIR / f"no_images_{abs(hash(url))}.png"
        await tab.screenshot(str(screenshot_path))
        
        return str(screenshot_path)


# ============================================================
# 5. HAR RECORDING
# ============================================================

async def record_har(url: str, har_path: str = "recording.har") -> Dict[str, Any]:
    """
    Записывает HAR (HTTP Archive) при загрузке страницы
    """
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        
        async with tab.request.record() as capture:
            await tab.go_to(url)
            await asyncio.sleep(3)
        
        capture.save(har_path)
        
        return {
            "entries_count": len(capture.entries),
            "file_path": har_path
        }


# ============================================================
# 6. HYBRID AUTOMATION (UI + API)
# ============================================================

async def hybrid_automation_example(login_url: str, username: str, password: str, api_url: str) -> Dict[str, Any]:
    """
    Пример гибридной автоматизации: логин через UI, затем API-запрос
    """
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        
        # Шаг 1: Логинимся через UI
        await tab.go_to(login_url)
        
        username_field = await tab.find(id='username')
        await username_field.type_text(username)
        
        password_field = await tab.find(id='password')
        await password_field.type_text(password)
        
        login_btn = await tab.find(id='login-btn')
        await login_btn.click()
        
        await asyncio.sleep(2)
        
        # Шаг 2: Делаем API-запрос, который наследует сессию браузера
        response = await tab.request.get(api_url)
        
        return {
            "status": response.status,
            "data": response.json() if response.is_json else response.text[:200]
        }


# ============================================================
# 7. PAGE BUNDLES
# ============================================================

async def save_page_bundle(url: str, bundle_path: str = "page.zip", inline: bool = False) -> str:
    """
    Сохраняет страницу и все ресурсы в ZIP-архив
    """
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.go_to(url)
        await asyncio.sleep(2)
        
        if inline:
            await tab.save_bundle(bundle_path, inline_assets=True)
        else:
            await tab.save_bundle(bundle_path)
        
        return bundle_path


# ============================================================
# 8. HUMANIZED MOUSE MOVEMENT
# ============================================================

async def human_click_example(url: str, selector: str) -> str:
    """
    Кликает по элементу с человеко-подобным движением мыши
    """
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.go_to(url)
        
        element = await tab.find(css_selector=selector)
        await element.click(humanize=True)
        
        await asyncio.sleep(1)
        
        screenshot_path = SCREENSHOTS_DIR / f"human_click_{abs(hash(selector))}.png"
        await tab.screenshot(str(screenshot_path))
        
        return str(screenshot_path)


# ============================================================
# 9. CONCURRENT TABS
# ============================================================

async def concurrent_scraping(urls: List[str]) -> List[str]:
    """
    Открывает несколько вкладок параллельно
    """
    options = get_optimized_options()
    
    async def scrape_page(url: str, tab) -> str:
        await tab.go_to(url)
        return await tab.title
    
    async with Chrome(options=options) as browser:
        tabs = []
        for i, url in enumerate(urls):
            if i == 0:
                tab = await browser.start()
            else:
                tab = await browser.new_tab()
            tabs.append(tab)
        
        results = await asyncio.gather(
            *[scrape_page(url, tab) for url, tab in zip(urls, tabs)]
        )
        
        return results


# ============================================================
# 10. СТРУКТУРИРОВАННЫЙ ПАРСИНГ (ExtractionModel)
# ============================================================

class QuoteModel(ExtractionModel):
    """Модель для парсинга цитат"""
    text: str = Field(selector='.text', description='Текст цитаты')
    author: str = Field(selector='.author', description='Автор')
    tags: list[str] = Field(selector='.tag', description='Теги')

async def extract_quotes(url: str) -> list[dict]:
    """
    Парсит цитаты со страницы, используя Pydoll Extractor
    """
    options = get_optimized_options()
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.go_to(url)
        
        quotes = await tab.extract_all(QuoteModel, scope='.quote', timeout=5)
        
        return [q.model_dump() for q in quotes]