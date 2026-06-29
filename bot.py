# bot.py
import os
import sys
import subprocess
import json
import logging
import traceback
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Импорт джойстика
from joystick_controller import JoystickController

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

PLAYWRIGHT_DIR = "/root/.cache/ms-playwright"
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = PLAYWRIGHT_DIR

# Куки X.com
COOKIES = [
    {"name": "__cuid", "value": "55d2d7c5-4888-430a-b024-dd785da46ef4", "domain": ".x.com", "path": "/"},
    {"name": "lang", "value": "ru", "domain": ".x.com", "path": "/"},
    {"name": "dnt", "value": "1", "domain": ".x.com", "path": "/"},
    {"name": "guest_id", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_marketing", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_ads", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "personalization_id", "value": "\"v1_DKrxLZAC902dMFdd1QrVYg==\"", "domain": ".x.com", "path": "/"},
    {"name": "gt", "value": "2071329406237220892", "domain": ".x.com", "path": "/"},
    {"name": "__cf_bm", "value": ".I7b6GGmlN4fNcwOMuw9lT0dsT0ARfcIVwJt0bKVn1A-1782678389.549309-1.0.1.1-ZyWyQlXJpxNQRq6_2VYG2dr8Gz2iv_dZ2DrW2mnM.xR8yrtzsdhU310hzPoDkIQZYC6QGWKef5dCUOQQKZdp5_AmnVQS5zZ1p67ydtzPrydFxyV6zl740zd69v0Xs3JC", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"}
]

browser_data = None
error_logs = []
MAX_LOGS = 50
browser_lock = False

def log_error(error_msg, traceback_str=None):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = {
        'time': timestamp,
        'error': error_msg,
        'traceback': traceback_str
    }
    error_logs.append(log_entry)
    if len(error_logs) > MAX_LOGS:
        error_logs.pop(0)
    logger.error(f"{error_msg}\n{traceback_str}" if traceback_str else error_msg)

def install_playwright_browser():
    browser_path = os.path.join(PLAYWRIGHT_DIR, "chromium-1091", "chrome-linux", "chrome")
    if os.path.exists(browser_path):
        print("✅ Браузер уже установлен")
        return True
    print("⏳ Устанавливаю браузер Chromium...")
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        subprocess.run([sys.executable, "-m", "playwright", "install-deps"], check=True)
        print("✅ Браузер успешно установлен!")
        return True
    except Exception as e:
        print(f"❌ Ошибка установки браузера: {e}")
        return False

install_playwright_browser()

async def get_browser():
    global browser_data, browser_lock
    
    from playwright.async_api import async_playwright
    from playwright_stealth import stealth_async
    
    if browser_data:
        try:
            await browser_data['page'].evaluate('1')
            return browser_data
        except:
            try:
                await browser_data['browser'].close()
            except:
                pass
            browser_data = None
    
    while browser_lock:
        await asyncio.sleep(0.5)
    
    browser_lock = True
    
    try:
        p = await async_playwright().start()
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
                '--disable-features=BlockInsecurePrivateNetworkRequests',
                '--disable-gpu',
                '--disable-software-rasterizer'
            ]
        )
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720},
            locale='en-US',
            timezone_id='America/New_York',
            permissions=['geolocation'],
            device_scale_factor=1,
            has_touch=False,
            is_mobile=False,
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
                'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"'
            }
        )
        page = await context.new_page()
        await stealth_async(page)
        
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            window.chrome = {
                runtime: {}
            };
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 4
            });
        """)
        
        browser_data = {
            'playwright': p,
            'browser': browser,
            'context': context,
            'page': page
        }
        
        return browser_data
    finally:
        browser_lock = False

async def close_browser():
    global browser_data, browser_lock
    
    if browser_data:
        try:
            await browser_data['browser'].close()
            await browser_data['playwright'].stop()
        except:
            pass
        browser_data = None

# ========== ОСНОВНЫЕ КОМАНДЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот с браузером Playwright + Джойстик\n\n"
        "📌 Основные команды:\n"
        "/go <url> - открыть сайт\n"
        "/xlogin - вход в X.com\n"
        "/screen - скриншот\n"
        "/status - состояние браузера\n"
        "/check - проверка авторизации\n"
        "/close - закрыть браузер\n\n"
        "🎮 Команды джойстика:\n"
        "/joystick - тест джойстика\n"
        "/joystick_ai <задача> - AI поиск и клик\n"
        "/find <запрос> - найти элементы\n"
        "/click <testid> - клик по testid\n"
        "/findbuttons - все кнопки"
    )

async def go(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /go https://example.com")
        return
    
    url = context.args[0]
    if not url.startswith('http'):
        url = 'https://' + url
    
    msg = await update.message.reply_text(f"⏳ Открываю {url}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        await page.goto(url, wait_until='domcontentloaded', timeout=15000)
        await msg.edit_text(f"✅ Открыл: {url}")
    except Exception as e:
        error_msg = f"Ошибка в go: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def xlogin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Захожу в X.com...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        logger.info(f"User {update.effective_user.id} начал xlogin")
        
        await page.goto('about:blank')
        await page.wait_for_timeout(1000)
        
        try:
            await browser['context'].clear_cookies()
            logger.info("Старые куки очищены")
        except Exception as e:
            logger.warning(f"Ошибка очистки кук: {e}")
            await close_browser()
            browser = await get_browser()
            page = browser['page']
        
        cookie_errors = []
        cookie_success = []
        
        for cookie in COOKIES:
            try:
                await browser['context'].add_cookies([cookie])
                cookie_success.append(cookie['name'])
            except Exception as e:
                error_msg = f"Ошибка установки куки {cookie['name']}: {str(e)}"
                cookie_errors.append(error_msg)
                logger.warning(error_msg)
        
        log_msg = f"✅ Установлено кук: {len(cookie_success)}\n"
        log_msg += f"❌ Ошибок: {len(cookie_errors)}\n"
        
        if cookie_errors:
            log_msg += f"\n⚠️ Ошибки установки:\n" + "\n".join(cookie_errors[:3])
            if len(cookie_errors) > 3:
                log_msg += f"\n... и еще {len(cookie_errors)-3}"
        
        log_msg += "\n\n🔄 Перехожу на x.com..."
        try:
            await page.goto('https://x.com', wait_until='commit', timeout=15000)
            logger.info("Страница начала загрузку")
            await page.wait_for_timeout(5000)
            
            try:
                await page.wait_for_selector('body', timeout=10000)
                logger.info("Body загружен")
            except:
                logger.warning("Body не загружен")
            
        except Exception as e:
            error_msg = f"Ошибка загрузки: {str(e)}"
            log_error(error_msg, traceback.format_exc())
            log_msg += f"\n❌ {error_msg}"
            
            try:
                await page.reload(wait_until='domcontentloaded', timeout=15000)
                log_msg += "\n🔄 Страница перезагружена"
                await page.wait_for_timeout(3000)
            except:
                pass
        
        try:
            current_url = page.url
            log_msg += f"\n📍 URL: {current_url[:80]}"
        except:
            log_msg += f"\n📍 URL: Недоступен"
        
        is_logged = False
        try:
            selectors = [
                ("primary_column", '[data-testid="primaryColumn"]'),
                ("tweet_button", '[data-testid="tweetButton"]'),
                ("profile_link", '[data-testid="AppTabBar_Profile_Link"]'),
                ("login_form", '[data-testid="loginForm"]'),
                ("toast_error", '[data-testid="toast"]'),
                ("challenge", '[data-testid="challenge"]')
            ]
            
            selector_results = []
            for name, selector in selectors:
                try:
                    exists = await page.query_selector(selector) is not None
                    selector_results.append(f"{name}: {'✅' if exists else '❌'}")
                    if name == "primary_column" and exists:
                        is_logged = True
                except Exception as e:
                    selector_results.append(f"{name}: ⚠️ ошибка")
            
            log_msg += "\n\n🔍 Элементы:\n" + "\n".join(selector_results)
            
        except Exception as e:
            log_msg += f"\n\n⚠️ Ошибка проверки элементов: {str(e)}"
        
        try:
            cookies_in_browser = await browser['context'].cookies()
            auth_token = next((c for c in cookies_in_browser if c.get('name') == 'auth_token'), None)
            log_msg += f"\n\n🍪 Кук: {len(cookies_in_browser)}"
            log_msg += f"\n🔑 auth_token: {'✅' if auth_token else '❌'}"
        except Exception as e:
            log_msg += f"\n\n⚠️ Ошибка проверки кук: {str(e)}"
        
        try:
            title = await page.title()
            log_msg += f"\n\n📌 Заголовок: {title[:60] if title else 'Нет заголовка'}"
        except:
            log_msg += f"\n\n📌 Заголовок: Недоступен"
        
        screenshot = None
        try:
            screenshot = await page.screenshot(
                full_page=False,
                type='jpeg',
                quality=80
            )
            log_msg += f"\n\n📸 Скриншот сделан"
        except Exception as e:
            log_msg += f"\n\n⚠️ Ошибка скриншота: {str(e)}"
        
        await msg.edit_text(
            f"✅ Зашёл в X.com!\n\n{log_msg}"
        )
        
        if screenshot:
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"📸 Скриншот {datetime.now().strftime('%H:%M:%S')}"
            )
        
        logger.info(f"xlogin завершен, статус: {is_logged}")
        
    except Exception as e:
        error_msg = f"Критическая ошибка: {str(e)}"
        traceback_str = traceback.format_exc()
        log_error(error_msg, traceback_str)
        
        if "closed" in str(e).lower():
            await close_browser()
            await msg.edit_text("❌ Браузер закрыт. Попробуйте снова /xlogin")
        else:
            await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Делаю скриншот...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        screenshot = await page.screenshot(
            full_page=False,
            type='jpeg',
            quality=80
        )
        
        await msg.delete()
        await update.message.reply_photo(
            photo=screenshot,
            caption="📸 Скриншот текущей страницы"
        )
    except Exception as e:
        error_msg = f"Ошибка в screen: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Проверка браузера...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        url = page.url
        title = await page.title()
        
        await msg.edit_text(
            f"✅ Браузер работает!\n"
            f"📌 Страница: {title[:40] if title else 'Нет заголовка'}\n"
            f"🔗 URL: {url[:50]}"
        )
    except Exception as e:
        error_msg = f"Ошибка в status: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_data
    
    browser_path = os.path.join(PLAYWRIGHT_DIR, "chromium-1091", "chrome-linux", "chrome")
    installed = os.path.exists(browser_path)
    
    is_open = "❌"
    url = "Нет"
    if browser_data:
        try:
            page = browser_data['page']
            url = page.url
            is_open = "✅"
        except:
            is_open = "❌ (закрыт)"
    
    await update.message.reply_text(
        f"📊 Статистика\n\n"
        f"🕐 Время: {datetime.now().strftime('%H:%M:%S')}\n"
        f"🌐 Браузер: {'✅' if installed else '❌'}\n"
        f"📂 Браузер открыт: {is_open}\n"
        f"🔗 Текущий URL: {url[:50]}\n"
        f"🍪 Куки: {len(COOKIES)} шт."
    )

async def check_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Проверяю статус...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        checks = {
            'primary_column': await page.query_selector('[data-testid="primaryColumn"]'),
            'tweet_button': await page.query_selector('[data-testid="tweetButton"]'),
            'profile_link': await page.query_selector('[data-testid="AppTabBar_Profile_Link"]'),
            'login_form': await page.query_selector('[data-testid="loginForm"]'),
            'challenge': await page.query_selector('[data-testid="challenge"]')
        }
        
        status_msg = "🔍 СТАТУС АВТОРИЗАЦИИ:\n\n"
        for name, element in checks.items():
            status_msg += f"{name}: {'✅' if element else '❌'}\n"
        
        cookies = await browser['context'].cookies()
        auth_token = next((c for c in cookies if c.get('name') == 'auth_token'), None)
        ct0 = next((c for c in cookies if c.get('name') == 'ct0'), None)
        
        status_msg += f"\n🍪 auth_token: {'✅' if auth_token else '❌'}"
        status_msg += f"\n🍪 ct0: {'✅' if ct0 else '❌'}"
        
        try:
            current_url = page.url
            status_msg += f"\n\n📍 URL: {current_url[:80]}"
        except:
            status_msg += f"\n\n📍 URL: Недоступен"
        
        try:
            title = await page.title()
            status_msg += f"\n📌 Заголовок: {title[:60] if title else 'Нет'}"
        except:
            status_msg += f"\n📌 Заголовок: Недоступен"
        
        status_msg += "\n\n"
        if checks['primary_column'] and checks['profile_link'] and checks['tweet_button']:
            status_msg += "✅ ПОЛНАЯ АВТОРИЗАЦИЯ!"
        elif checks['primary_column'] and checks['profile_link']:
            status_msg += "⚠️ ЧАСТИЧНАЯ АВТОРИЗАЦИЯ (не хватает кнопок)"
        elif checks['primary_column']:
            status_msg += "⚠️ ЧАСТИЧНАЯ АВТОРИЗАЦИЯ (только основная колонка)"
        elif checks['login_form']:
            status_msg += "❌ ТРЕБУЕТСЯ ВХОД"
        elif checks['challenge']:
            status_msg += "⚠️ ТРЕБУЕТСЯ ПРОВЕРКА (капча/Cloudflare)"
        else:
            status_msg += "❌ СТАТУС НЕ ОПРЕДЕЛЕН"
        
        await msg.edit_text(status_msg)
        
    except Exception as e:
        error_msg = f"Ошибка в check_auth: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def show_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Загружаю логи...")
    
    try:
        if error_logs:
            log_text = "📋 Последние ошибки:\n\n"
            for i, log in enumerate(error_logs[-10:], 1):
                log_text += f"{i}. 🕐 {log['time']}\n"
                log_text += f"   ❌ {log['error'][:100]}\n"
                if log.get('traceback'):
                    traceback_preview = log['traceback'].split('\n')[-3:]
                    log_text += f"   📍 {traceback_preview[0][:60]}\n"
                log_text += "\n"
        else:
            log_text = "✅ Ошибок нет"
        
        try:
            with open('bot.log', 'r') as f:
                lines = f.readlines()
                if lines:
                    log_text += "\n📄 Последние записи из файла:\n"
                    last_lines = lines[-5:]
                    log_text += "".join(last_lines)
        except:
            pass
        
        if len(log_text) > 4000:
            with open('logs_temp.txt', 'w') as f:
                f.write(log_text)
            await update.message.reply_document(
                document=open('logs_temp.txt', 'rb'),
                filename=f"logs_{datetime.now().strftime('%Y%m%d')}.txt"
            )
            os.remove('logs_temp.txt')
        else:
            await msg.edit_text(log_text)
            
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка при загрузке логов: {str(e)}")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Закрываю браузер...")
    await close_browser()
    await msg.edit_text("✅ Браузер закрыт!")

# ========== КОМАНДЫ ДЖОЙСТИКА ==========

async def joystick_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестирование джойстика"""
    msg = await update.message.reply_text("🎮 Тестирую джойстик...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        joystick = JoystickController(page)
        await joystick.init_position()
        
        await msg.edit_text("🔄 Круг...")
        await joystick.move_with_pattern('circle', duration=2.0, size=150)
        
        await msg.edit_text("🔄 Квадрат...")
        await joystick.move_with_pattern('square', duration=2.0, size=150)
        
        await msg.edit_text("🔄 Спираль...")
        await joystick.move_with_pattern('spiral', duration=2.0, size=100)
        
        elements = await joystick.explore_screen()
        
        result = "🎮 ДЖОЙСТИК ТЕСТ\n\n"
        result += f"Найдено элементов: {len(elements)}\n\n"
        
        for i, el in enumerate(elements[:5], 1):
            result += f"{i}. {el['tag']}: {el['text'][:30]}\n"
            result += f"   📍 ({int(el['x'])}, {int(el['y'])})\n"
            result += f"   📐 {int(el['width'])}×{int(el['height'])}\n"
            if el['testid']:
                result += f"   🏷️ testid: {el['testid']}\n"
            result += "\n"
        
        await msg.edit_text(result)
        
    except Exception as e:
        error_msg = f"Ошибка в joystick_test: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def joystick_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """AI агент управляет мышью"""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи задачу для AI\n"
            "Пример: /joystick_ai найти кнопку Обзор\n"
            "Пример: /joystick_ai нажать на Войти"
        )
        return
    
    task = ' '.join(context.args)
    msg = await update.message.reply_text(f"🤖 AI ищет: {task}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        joystick = JoystickController(page)
        await joystick.init_position()
        
        elements = await joystick.explore_screen()
        
        # Ищем подходящий элемент
        found = None
        best_score = 0
        
        for el in elements:
            score = 0
            text_lower = el['text'].lower()
            testid_lower = el['testid'].lower()
            aria_lower = el['ariaLabel'].lower()
            
            # Проверяем каждое слово из запроса
            for word in task.lower().split():
                if word in text_lower:
                    score += 3
                if word in testid_lower:
                    score += 2
                if word in aria_lower:
                    score += 2
                # Проверяем частичное совпадение
                for part in [text_lower, testid_lower, aria_lower]:
                    if word in part and len(word) > 2:
                        score += 1
            
            if score > best_score:
                best_score = score
                found = el
        
        if found and best_score > 0:
            # Движение к элементу
            await joystick.human_like_move(found['x'], found['y'])
            await asyncio.sleep(0.3)
            
            # Клик
            await joystick.click()
            
            await msg.edit_text(
                f"✅ AI нашел и нажал!\n\n"
                f"📌 Элемент: {found['tag']}\n"
                f"📝 Текст: {found['text'][:50]}\n"
                f"🏷️ testid: {found['testid'] or 'нет'}\n"
                f"📍 Координаты: ({int(found['x'])}, {int(found['y'])})\n"
                f"🎯 Точность: {best_score} баллов"
            )
        else:
            # Показываем доступные элементы
            result = f"❌ AI не нашел подходящий элемент\n\n"
            result += f"Найдено элементов: {len(elements)}\n"
            result += f"Запрос: {task}\n\n"
            result += "📋 Доступные элементы:\n"
            
            for i, el in enumerate(elements[:10], 1):
                result += f"{i}. {el['tag']}: {el['text'][:30]}\n"
                if el['testid']:
                    result += f"   🏷️ {el['testid']}\n"
            
            if len(elements) > 10:
                result += f"\n... и еще {len(elements) - 10} элементов"
            
            await msg.edit_text(result)
            
    except Exception as e:
        error_msg = f"Ошибка в joystick_ai: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def find_elements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Находит элементы по запросу"""
    if not context.args:
        await update.message.reply_text(
            "❌ Что ищем?\n"
            "Пример: /find кнопка Войти\n"
            "Пример: /find testid tweetButton\n"
            "Пример: /find профиль"
        )
        return
    
    query = ' '.join(context.args)
    msg = await update.message.reply_text(f"🔍 Ищу: {query}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        joystick = JoystickController(page)
        await joystick.init_position()
        
        elements = await joystick.explore_screen()
        
        # Фильтруем
        found = []
        for el in elements:
            text = el['text'].lower()
            testid = el['testid'].lower()
            aria = el['ariaLabel'].lower()
            el_id = el['id'].lower()
            tag = el['tag'].lower()
            
            if (query.lower() in text or 
                query.lower() in testid or
                query.lower() in aria or
                query.lower() in el_id or
                query.lower() in tag):
                found.append(el)
        
        if found:
            result = f"✅ Найдено {len(found)} элементов:\n\n"
            for i, el in enumerate(found[:10], 1):
                result += f"{i}. {el['tag']}"
                if el['type']:
                    result += f" [{el['type']}]"
                result += f": {el['text'][:30]}\n"
                result += f"   📍 ({int(el['x'])}, {int(el['y'])})\n"
                if el['testid']:
                    result += f"   🏷️ testid: {el['testid']}\n"
                if el['id']:
                    result += f"   🔑 id: {el['id']}\n"
                result += "\n"
            
            if len(found) > 10:
                result += f"... и еще {len(found) - 10} элементов"
            
            # Показываем первый найденный
            if found:
                await joystick.human_like_move(found[0]['x'], found[0]['y'])
                result += "\n\n🖱️ Курсор наведен на первый элемент"
            
            await msg.edit_text(result)
        else:
            await msg.edit_text(
                f"❌ Ничего не найдено по запросу: {query}\n\n"
                f"Всего элементов на странице: {len(elements)}"
            )
            
    except Exception as e:
        error_msg = f"Ошибка в find_elements: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def findbuttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Находит все кнопки на странице"""
    msg = await update.message.reply_text("⏳ Ищу кнопки...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        joystick = JoystickController(page)
        await joystick.init_position()
        
        elements = await joystick.explore_screen()
        
        # Фильтруем только кнопки
        buttons = [el for el in elements if el['tag'] == 'button' or 'button' in el.get('role', '')]
        
        if buttons:
            result = "🔘 НАЙДЕННЫЕ КНОПКИ:\n\n"
            for i, btn in enumerate(buttons[:30], 1):
                result += f"{i}. {btn['text'][:50] or 'без текста'}\n"
                if btn['testid']:
                    result += f"   🏷️ {btn['testid']}\n"
                if btn['ariaLabel']:
                    result += f"   🏷️ aria-label: {btn['ariaLabel']}\n"
                result += f"   📍 ({int(btn['x'])}, {int(btn['y'])})\n\n"
            
            if len(buttons) > 30:
                result += f"... и еще {len(buttons) - 30} кнопок"
            else:
                result += f"Всего кнопок: {len(buttons)}"
            
            if len(result) > 4000:
                with open('buttons.txt', 'w') as f:
                    f.write(result)
                await update.message.reply_document(
                    document=open('buttons.txt', 'rb'),
                    filename=f"buttons_{datetime.now().strftime('%Y%m%d')}.txt"
                )
                os.remove('buttons.txt')
            else:
                await msg.edit_text(result)
        else:
            await msg.edit_text("❌ Кнопки не найдены")
            
    except Exception as e:
        error_msg = f"Ошибка в findbuttons: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def click_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Нажимает кнопку по data-testid с использованием джойстика"""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи data-testid кнопки\n"
            "Пример: /click AppTabBar_Explore_Link\n\n"
            "📌 Доступные кнопки:\n"
            "• AppTabBar_Home_Link - Главная\n"
            "• AppTabBar_Explore_Link - Обзор\n"
            "• AppTabBar_Notifications_Link - Уведомления\n"
            "• AppTabBar_Profile_Link - Профиль\n"
            "• AppTabBar_DirectMessage_Link - Чат\n"
            "• SideNav_NewTweet_Button - Новый пост\n"
            "• tweetButton - Опубликовать\n"
            "• reply - Ответить\n"
            "• retweet - Репост\n"
            "• like - Нравится\n"
            "• bookmark - Закладка"
        )
        return
    
    testid = context.args[0]
    msg = await update.message.reply_text(f"⏳ Ищу кнопку {testid}...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        joystick = JoystickController(page)
        await joystick.init_position()
        
        # Используем джойстик для поиска и клика
        selector = f'[data-testid="{testid}"]'
        success = await joystick.move_to_element(selector)
        
        if not success:
            await msg.edit_text(f"❌ Кнопка {testid} не найдена")
            return
        
        await joystick.click()
        await asyncio.sleep(1)
        
        screenshot = await page.screenshot(
            full_page=False,
            type='jpeg',
            quality=80
        )
        
        await msg.edit_text(f"✅ Нажал на {testid}")
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"📸 После клика на {testid}"
        )
        
    except Exception as e:
        error_msg = f"Ошибка в click_button: {str(e)}"
        log_error(error_msg, traceback.format_exc())
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

# ========== ЗАПУСК ==========

def main():
    app = Application.builder().token(TOKEN).build()
    
    # Основные команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("go", go))
    app.add_handler(CommandHandler("xlogin", xlogin))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("check", check_auth))
    app.add_handler(CommandHandler("logs", show_logs))
    app.add_handler(CommandHandler("close", close))
    
    # Команды джойстика
    app.add_handler(CommandHandler("joystick", joystick_test))
    app.add_handler(CommandHandler("joystick_ai", joystick_ai))
    app.add_handler(CommandHandler("find", find_elements))
    app.add_handler(CommandHandler("findbuttons", findbuttons))
    app.add_handler(CommandHandler("click", click_button))
    
    print("🤖 Бот с джойстиком запущен...")
    print("📌 Доступные команды:")
    print("   Основные: /start, /go, /xlogin, /screen, /status, /check, /close")
    print("   Джойстик: /joystick, /joystick_ai, /find, /findbuttons, /click")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()