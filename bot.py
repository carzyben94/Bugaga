# x_scanner.py - Бот для полного сканирования X.com
import os
import sys
import subprocess
import json
import asyncio
import logging
import traceback
from datetime import datetime
from typing import List, Dict, Any
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

PLAYWRIGHT_DIR = "/root/.cache/ms-playwright"
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = PLAYWRIGHT_DIR

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Куки X.com (все как было)
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

# Глобальные переменные
browser_data = None
browser_lock = False
scan_results = {}

# ========== УСТАНОВКА БРАУЗЕРА (как было) ==========
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

# ========== УПРАВЛЕНИЕ БРАУЗЕРОМ (как было) ==========
async def get_browser():
    global browser_data, browser_lock
    
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
        
        # Устанавливаем куки
        for cookie in COOKIES:
            try:
                await context.add_cookies([cookie])
            except Exception as e:
                logger.warning(f"Ошибка установки куки {cookie['name']}: {e}")
        
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

# ========== СКАНЕР X.COM ==========
class XScanner:
    def __init__(self, page):
        self.page = page
        self.results = {
            'url': '',
            'title': '',
            'buttons': [],
            'links': [],
            'forms': [],
            'testids': {},
            'tweets': [],
            'navigation': [],
            'profile': {},
            'selectors': {},
            'timestamp': datetime.now().isoformat()
        }
    
    async def scan_full(self):
        """Полное сканирование страницы"""
        logger.info("🔍 Начинаю полное сканирование...")
        
        self.results['url'] = self.page.url
        self.results['title'] = await self.page.title()
        
        await self.scan_buttons()
        await self.scan_links()
        await self.scan_forms()
        await self.scan_testids()
        await self.scan_tweets()
        await self.scan_navigation()
        await self.scan_profile()
        await self.scan_selectors()
        
        self.results['stats'] = {
            'total_buttons': len(self.results['buttons']),
            'total_links': len(self.results['links']),
            'total_forms': len(self.results['forms']),
            'total_testids': len(self.results['testids']),
            'total_tweets': len(self.results['tweets'])
        }
        
        logger.info(f"✅ Сканирование завершено!")
        return self.results
    
    async def scan_buttons(self):
        buttons = await self.page.evaluate('''
            () => {
                const result = [];
                document.querySelectorAll('button, [role="button"], [data-testid*="button"]').forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        result.push({
                            text: el.textContent?.trim()?.slice(0, 50) || '',
                            testid: el.getAttribute('data-testid') || '',
                            ariaLabel: el.getAttribute('aria-label') || '',
                            type: el.getAttribute('type') || '',
                            class: el.className?.slice(0, 50) || '',
                            x: Math.round(rect.x + rect.width/2),
                            y: Math.round(rect.y + rect.height/2)
                        });
                    }
                });
                return result;
            }
        ''')
        self.results['buttons'] = buttons
        logger.info(f"🔘 Найдено кнопок: {len(buttons)}")
    
    async def scan_links(self):
        links = await self.page.evaluate('''
            () => {
                const result = [];
                document.querySelectorAll('a[href]').forEach(el => {
                    const href = el.getAttribute('href');
                    if (href && !href.startsWith('javascript:')) {
                        result.push({
                            href: href.slice(0, 100),
                            text: el.textContent?.trim()?.slice(0, 50) || '',
                            title: el.getAttribute('title') || '',
                            ariaLabel: el.getAttribute('aria-label') || ''
                        });
                    }
                });
                return result;
            }
        ''')
        self.results['links'] = links
        logger.info(f"🔗 Найдено ссылок: {len(links)}")
    
    async def scan_forms(self):
        forms = await self.page.evaluate('''
            () => {
                const result = [];
                document.querySelectorAll('form').forEach(el => {
                    const inputs = [];
                    el.querySelectorAll('input, textarea, select').forEach(input => {
                        inputs.push({
                            type: input.getAttribute('type') || input.tagName.toLowerCase(),
                            name: input.getAttribute('name') || '',
                            placeholder: input.getAttribute('placeholder') || '',
                            testid: input.getAttribute('data-testid') || ''
                        });
                    });
                    result.push({
                        action: el.getAttribute('action') || '',
                        method: el.getAttribute('method') || 'get',
                        inputs: inputs
                    });
                });
                return result;
            }
        ''')
        self.results['forms'] = forms
        logger.info(f"📝 Найдено форм: {len(forms)}")
    
    async def scan_testids(self):
        testids = await self.page.evaluate('''
            () => {
                const result = {};
                document.querySelectorAll('[data-testid]').forEach(el => {
                    const id = el.getAttribute('data-testid');
                    if (id) {
                        if (!result[id]) result[id] = 0;
                        result[id]++;
                    }
                });
                return result;
            }
        ''')
        self.results['testids'] = testids
        logger.info(f"🏷️ Найдено testid: {len(testids)}")
    
    async def scan_tweets(self):
        tweets = await self.page.evaluate('''
            () => {
                const result = [];
                document.querySelectorAll('[data-testid="tweet"]').forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        const text = el.textContent?.trim() || '';
                        const authorEl = el.querySelector('[data-testid="User-Name"]');
                        const timeEl = el.querySelector('time');
                        const likeEl = el.querySelector('[data-testid="like"]');
                        const retweetEl = el.querySelector('[data-testid="retweet"]');
                        const replyEl = el.querySelector('[data-testid="reply"]');
                        
                        result.push({
                            text: text.slice(0, 200),
                            author: authorEl?.textContent?.trim() || 'Unknown',
                            time: timeEl?.getAttribute('datetime') || '',
                            likes: likeEl?.textContent?.trim() || '0',
                            retweets: retweetEl?.textContent?.trim() || '0',
                            replies: replyEl?.textContent?.trim() || '0'
                        });
                    }
                });
                return result;
            }
        ''')
        self.results['tweets'] = tweets
        logger.info(f"🐦 Найдено постов: {len(tweets)}")
    
    async def scan_navigation(self):
        nav = await self.page.evaluate('''
            () => {
                const result = [];
                const items = [
                    'AppTabBar_Home_Link',
                    'AppTabBar_Explore_Link', 
                    'AppTabBar_Notifications_Link',
                    'AppTabBar_Profile_Link',
                    'AppTabBar_DirectMessage_Link'
                ];
                items.forEach(id => {
                    const el = document.querySelector(`[data-testid="${id}"]`);
                    if (el) {
                        result.push({
                            testid: id,
                            text: el.textContent?.trim() || ''
                        });
                    }
                });
                return result;
            }
        ''')
        self.results['navigation'] = nav
        logger.info(f"🧭 Найдено навигации: {len(nav)}")
    
    async def scan_profile(self):
        profile = await self.page.evaluate('''
            () => {
                const result = {};
                const name = document.querySelector('[data-testid="UserName"]');
                if (name) result.name = name.textContent?.trim() || '';
                
                const bio = document.querySelector('[data-testid="UserDescription"]');
                if (bio) result.bio = bio.textContent?.trim() || '';
                
                return result;
            }
        ''')
        self.results['profile'] = profile
        logger.info(f"👤 Профиль: {profile.get('name', 'Не найден')}")
    
    async def scan_selectors(self):
        selectors = await self.page.evaluate('''
            () => {
                const result = {
                    tweet_button: !!document.querySelector('[data-testid="tweetButton"]'),
                    like: !!document.querySelector('[data-testid="like"]'),
                    retweet: !!document.querySelector('[data-testid="retweet"]'),
                    reply: !!document.querySelector('[data-testid="reply"]'),
                    bookmark: !!document.querySelector('[data-testid="bookmark"]')
                };
                return result;
            }
        ''')
        self.results['selectors'] = selectors
        logger.info(f"📋 Доступных функций: {sum(1 for v in selectors.values() if v)}")

# ========== КОМАНДЫ ТЕЛЕГРАМ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **X.com Scanner Bot**\n\n"
        "📌 Команды:\n"
        "/xlogin - войти в X.com\n"
        "/scan - полное сканирование\n"
        "/report - показать отчет\n"
        "/export - экспорт JSON\n"
        "/status - статус браузера\n"
        "/close - закрыть браузер\n\n"
        "После /scan бот соберет все данные для будущих функций!"
    )

async def xlogin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Захожу в X.com...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        await page.goto('https://x.com', wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(3)
        
        is_logged = await page.query_selector('[data-testid="tweetButton"]') is not None
        
        if is_logged:
            await msg.edit_text("✅ Успешный вход в X.com!")
        else:
            await msg.edit_text("⚠️ Проверка входа...")
        
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await update.message.reply_photo(photo=screenshot, caption="📸 X.com")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Начинаю сканирование X.com...\n⏳ Это займет 10-20 секунд")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        if 'x.com' not in page.url:
            await msg.edit_text("❌ Сначала зайди на X.com через /xlogin")
            return
        
        scanner = XScanner(page)
        results = await scanner.scan_full()
        
        global scan_results
        scan_results = results
        
        # Отчет
        report = f"📊 **ОТЧЕТ О СКАНИРОВАНИИ**\n\n"
        report += f"📍 {results['url'][:60]}\n"
        report += f"📌 {results['title'][:50]}\n\n"
        
        report += f"**СТАТИСТИКА:**\n"
        report += f"🔘 Кнопок: {results['stats']['total_buttons']}\n"
        report += f"🔗 Ссылок: {results['stats']['total_links']}\n"
        report += f"📝 Форм: {results['stats']['total_forms']}\n"
        report += f"🏷️ TestID: {results['stats']['total_testids']}\n"
        report += f"🐦 Постов: {results['stats']['total_tweets']}\n\n"
        
        if results['testids']:
            report += f"**ОСНОВНЫЕ TESTID:**\n"
            sorted_ids = sorted(results['testids'].items(), key=lambda x: x[1], reverse=True)[:5]
            for testid, count in sorted_ids:
                report += f"• `{testid}`: {count} шт.\n"
        
        await msg.edit_text(report)
        
        # JSON
        filename = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        await update.message.reply_document(
            document=open(filename, 'rb'),
            filename=filename,
            caption="📄 Полный отчет"
        )
        os.remove(filename)
        
        # Скриншот
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await update.message.reply_photo(photo=screenshot, caption="📸 Страница")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(f"Scan error: {traceback.format_exc()}")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_results
    if not scan_results:
        await update.message.reply_text("❌ Нет данных. Сначала /scan")
        return
    
    report = f"📊 **ОТЧЕТ**\n\n"
    report += f"📍 {scan_results['url'][:60]}\n"
    report += f"📌 {scan_results['title'][:50]}\n\n"
    
    stats = scan_results.get('stats', {})
    report += f"🔘 {stats.get('total_buttons', 0)} кнопок\n"
    report += f"🔗 {stats.get('total_links', 0)} ссылок\n"
    report += f"🐦 {stats.get('total_tweets', 0)} постов\n"
    
    await update.message.reply_text(report)

async def export_json(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_results
    if not scan_results:
        await update.message.reply_text("❌ Нет данных. Сначала /scan")
        return
    
    filename = f"x_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(scan_results, f, ensure_ascii=False, indent=2)
    
    await update.message.reply_document(
        document=open(filename, 'rb'),
        filename=filename,
        caption="📄 Экспорт данных"
    )
    os.remove(filename)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_data
    if browser_data:
        try:
            page = browser_data['page']
            await update.message.reply_text(f"✅ Браузер активен\n📍 {page.url[:60]}")
        except:
            await update.message.reply_text("⚠️ Браузер не отвечает")
    else:
        await update.message.reply_text("❌ Браузер закрыт")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await close_browser()
    await update.message.reply_text("✅ Браузер закрыт")

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("xlogin", xlogin))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("export", export_json))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("close", close))
    
    print("🤖 X.com Scanner Bot запущен!")
    print("📌 Команды: /start, /xlogin, /scan, /report, /export")
    app.run_polling()

if __name__ == "__main__":
    main()