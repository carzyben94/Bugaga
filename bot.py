import os
import sys
import subprocess
import json
import logging
import traceback
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

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

# Свежие куки
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
browser_lock = False  # Блокировка для предотвращения конфликтов

def log_error(error_msg, traceback_str=None):
    """Сохраняет ошибку в лог"""
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
    
    # Проверяем существующий браузер
    if browser_data:
        try:
            # Проверяем жив ли браузер
            await browser_data['page'].evaluate('1')
            return browser_data
        except:
            try:
                await browser_data['browser'].close()
            except:
                pass
            browser_data = None
    
    # Ждем если браузер уже создается
    while browser_lock:
        await asyncio.sleep(0.5)
    
    browser_lock = True
    
    try:
        p = await async_playwright().start()
        browser = await p.chromium.launch(
            headless=True,  # Возвращаем в headless режим
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
                '--disable-features=BlockInsecurePrivateNetworkRequests'
            ]
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720},
            locale='en-US',
            timezone_id='America/New_York',
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0'
            }
        )
        page = await context.new_page()
        await stealth_async(page)
        
        # Добавляем скрипт для скрытия автоматизации
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот с браузером Playwright\n\n"
        "Доступные команды:\n"
        "/go <url> - открыть сайт\n"
        "/xlogin - вход в X.com\n"
        "/screen - скриншот\n"
        "/status - состояние браузера\n"
        "/stats - статистика\n"
        "/logs - показать логи\n"
        "/close - закрыть браузер"
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
        
        # Очищаем старые куки
        try:
            await browser['context'].clear_cookies()
            logger.info("Старые куки очищены")
        except Exception as e:
            logger.warning(f"Ошибка очистки кук: {e}")
            # Пересоздаем браузер если проблема
            await close_browser()
            browser = await get_browser()
            page = browser['page']
        
        # Устанавливаем новые куки с логированием
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
        
        # Переходим на страницу
        log_msg += "\n\n🔄 Перехожу на x.com..."
        try:
            # Ждем полной загрузки с таймаутом
            await page.goto('https://x.com', wait_until='networkidle', timeout=30000)
            logger.info("Страница загружена")
            
            # Дополнительная пауза для рендеринга
            await page.wait_for_timeout(3000)
            
        except Exception as e:
            error_msg = f"Ошибка загрузки страницы: {str(e)}"
            log_error(error_msg, traceback.format_exc())
            log_msg += f"\n❌ {error_msg}"
            
            # Пробуем перезагрузить страницу
            try:
                await page.reload(wait_until='domcontentloaded', timeout=15000)
                log_msg += "\n🔄 Страница перезагружена"
            except:
                pass
                
            await msg.edit_text(log_msg)
            return
        
        # Проверяем HTML страницы
        try:
            html_content = await page.content()
            log_msg += f"\n📄 HTML длина: {len(html_content)} символов"
            
            # Проверяем наличие ключевых слов
            if 'login' in html_content.lower():
                log_msg += "\n🔍 Найдено слово 'login' в HTML"
            if 'twitter' in html_content.lower() or 'x.com' in html_content.lower():
                log_msg += "\n🔍 Найдено 'twitter' или 'x.com' в HTML"
            if 'challenge' in html_content.lower():
                log_msg += "\n⚠️ Обнаружена страница проверки (challenge)"
            if 'cloudflare' in html_content.lower():
                log_msg += "\n⚠️ Обнаружена Cloudflare защита"
        except Exception as e:
            log_msg += f"\n⚠️ Ошибка проверки HTML: {str(e)}"
        
        # Проверяем URL (СВОЙСТВО - без await)
        try:
            current_url = page.url
            log_msg += f"\n📍 URL: {current_url[:80]}"
        except:
            log_msg += f"\n📍 URL: Недоступен"
        
        # Проверяем наличие элементов
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
            
            log_msg += "\n\n🔍 Элементы на странице:\n" + "\n".join(selector_results)
            
        except Exception as e:
            log_msg += f"\n\n⚠️ Ошибка проверки элементов: {str(e)}"
            log_error(f"Ошибка проверки селекторов: {str(e)}", traceback.format_exc())
        
        # Проверяем куки в браузере (МЕТОД - с await)
        try:
            cookies_in_browser = await browser['context'].cookies()
            auth_token = next((c for c in cookies_in_browser if c.get('name') == 'auth_token'), None)
            log_msg += f"\n\n🍪 Кук в браузере: {len(cookies_in_browser)}"
            log_msg += f"\n🔑 auth_token: {'✅ найден' if auth_token else '❌ не найден'}"
            
            if auth_token:
                expires = auth_token.get('expires')
                if expires:
                    expires_date = datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')
                    log_msg += f"\n📅 Истекает: {expires_date}"
        except Exception as e:
            log_msg += f"\n\n⚠️ Ошибка проверки кук: {str(e)}"
        
        # Заголовок страницы (МЕТОД - с await)
        try:
            title = await page.title()
            log_msg += f"\n\n📌 Заголовок: {title[:60] if title else 'Нет заголовка'}"
        except:
            log_msg += f"\n\n📌 Заголовок: Недоступен"
        
        # Делаем скриншот (МЕТОД - с await)
        screenshot = None
        try:
            screenshot = await page.screenshot()
            log_msg += f"\n\n📸 Скриншот сделан"
        except Exception as e:
            log_msg += f"\n\n⚠️ Ошибка создания скриншота: {str(e)}"
        
        # Отправляем результат
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
        error_msg = f"Критическая ошибка в xlogin: {str(e)}"
        traceback_str = traceback.format_exc()
        log_error(error_msg, traceback_str)
        
        # Если браузер закрыт, пробуем пересоздать
        if "closed" in str(e).lower():
            await close_browser()
            await msg.edit_text("❌ Браузер был закрыт. Попробуйте снова /xlogin")
        else:
            await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Делаю скриншот...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        screenshot = await page.screenshot(full_page=True)
        
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
        
        # page.url - СВОЙСТВО (без await)
        url = page.url
        # page.title() - МЕТОД (с await)
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
            # page.url - СВОЙСТВО (без await)
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

async def show_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает последние логи ошибок"""
    msg = await update.message.reply_text("⏳ Загружаю логи...")
    
    try:
        if error_logs:
            log_text = "📋 **Последние ошибки:**\n\n"
            for i, log in enumerate(error_logs[-10:], 1):
                log_text += f"{i}. 🕐 {log['time']}\n"
                log_text += f"   ❌ {log['error'][:100]}\n"
                if log.get('traceback'):
                    traceback_preview = log['traceback'].split('\n')[-3:]
                    log_text += f"   📍 {traceback_preview[0][:60]}\n"
                log_text += "\n"
        else:
            log_text = "✅ Ошибок нет"
        
        # Добавляем последние записи из файла
        try:
            with open('bot.log', 'r') as f:
                lines = f.readlines()
                if lines:
                    log_text += "\n📄 **Последние записи из файла:**\n"
                    last_lines = lines[-5:]
                    log_text += "```\n" + "".join(last_lines) + "```"
        except:
            pass
        
        if len(log_text) > 4000:
            # Отправляем файлом
            with open('logs_temp.txt', 'w') as f:
                f.write(log_text)
            await update.message.reply_document(
                document=open('logs_temp.txt', 'rb'),
                filename=f"logs_{datetime.now().strftime('%Y%m%d')}.txt"
            )
            os.remove('logs_temp.txt')
        else:
            await msg.edit_text(log_text, parse_mode='Markdown')
            
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка при загрузке логов: {str(e)}")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Закрываю браузер...")
    
    await close_browser()
    
    await msg.edit_text("✅ Браузер закрыт!")

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("go", go))
    app.add_handler(CommandHandler("xlogin", xlogin))
    app.add_handler(CommandHandler("screen", screen))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("logs", show_logs))
    app.add_handler(CommandHandler("close", close))
    
    print("🤖 Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()