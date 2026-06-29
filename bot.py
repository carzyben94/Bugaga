# x_scanner.py - Бот для полного сканирования X.com
import os
import json
import asyncio
import logging
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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Куки X.com
COOKIES = [
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
    {"name": "guest_id", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
]

# Глобальные переменные
browser_data = None
scan_results = {}

# ========== УПРАВЛЕНИЕ БРАУЗЕРОМ ==========
async def get_browser():
    global browser_data
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
    
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=True,
        args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
    )
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        viewport={'width': 1280, 'height': 720}
    )
    page = await context.new_page()
    await stealth_async(page)
    
    # Устанавливаем куки
    for cookie in COOKIES:
        try:
            await context.add_cookies([cookie])
        except:
            pass
    
    browser_data = {
        'playwright': p,
        'browser': browser,
        'context': context,
        'page': page
    }
    return browser_data

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
            'selectors': {},
            'navigation': [],
            'profile': {},
            'timestamp': datetime.now().isoformat()
        }
    
    async def scan_full(self):
        """Полное сканирование страницы"""
        logger.info("🔍 Начинаю полное сканирование...")
        
        # 1. Базовая информация
        self.results['url'] = self.page.url
        self.results['title'] = await self.page.title()
        
        # 2. Сканируем все элементы
        await self.scan_buttons()
        await self.scan_links()
        await self.scan_forms()
        await self.scan_testids()
        await self.scan_tweets()
        await self.scan_navigation()
        await self.scan_profile()
        await self.scan_selectors()
        
        # 3. Собираем статистику
        self.results['stats'] = {
            'total_buttons': len(self.results['buttons']),
            'total_links': len(self.results['links']),
            'total_forms': len(self.results['forms']),
            'total_testids': len(self.results['testids']),
            'total_tweets': len(self.results['tweets'])
        }
        
        logger.info(f"✅ Сканирование завершено! Найдено {self.results['stats']['total_tweets']} постов")
        return self.results
    
    async def scan_buttons(self):
        """Сканирует все кнопки"""
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
                            y: Math.round(rect.y + rect.height/2),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                            visible: true
                        });
                    }
                });
                return result;
            }
        ''')
        self.results['buttons'] = buttons
        logger.info(f"🔘 Найдено кнопок: {len(buttons)}")
    
    async def scan_links(self):
        """Сканирует все ссылки"""
        links = await self.page.evaluate('''
            () => {
                const result = [];
                document.querySelectorAll('a[href]').forEach(el => {
                    const href = el.getAttribute('href');
                    if (href && !href.startsWith('javascript:')) {
                        const rect = el.getBoundingClientRect();
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
        """Сканирует все формы"""
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
        """Собирает все data-testid"""
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
        logger.info(f"🏷️ Найдено data-testid: {len(testids)}")
    
    async def scan_tweets(self):
        """Сканирует все посты"""
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
                        const viewsEl = el.querySelector('[data-testid="views"]');
                        
                        result.push({
                            text: text.slice(0, 200),
                            author: authorEl?.textContent?.trim() || 'Unknown',
                            time: timeEl?.getAttribute('datetime') || '',
                            likes: likeEl?.textContent?.trim() || '0',
                            retweets: retweetEl?.textContent?.trim() || '0',
                            replies: replyEl?.textContent?.trim() || '0',
                            views: viewsEl?.textContent?.trim() || '',
                            x: Math.round(rect.x + rect.width/2),
                            y: Math.round(rect.y + rect.height/2)
                        });
                    }
                });
                return result;
            }
        ''')
        self.results['tweets'] = tweets
        logger.info(f"🐦 Найдено постов: {len(tweets)}")
    
    async def scan_navigation(self):
        """Сканирует элементы навигации"""
        nav = await self.page.evaluate('''
            () => {
                const result = [];
                const selectors = [
                    '[data-testid="AppTabBar_Home_Link"]',
                    '[data-testid="AppTabBar_Explore_Link"]',
                    '[data-testid="AppTabBar_Notifications_Link"]',
                    '[data-testid="AppTabBar_Profile_Link"]',
                    '[data-testid="AppTabBar_DirectMessage_Link"]',
                    '[data-testid="SideNav_NewTweet_Button"]'
                ];
                selectors.forEach(selector => {
                    const el = document.querySelector(selector);
                    if (el) {
                        result.push({
                            testid: selector.match(/AppTabBar_(.*)_Link/)?.[1] || selector,
                            present: true,
                            text: el.textContent?.trim() || ''
                        });
                    }
                });
                return result;
            }
        ''')
        self.results['navigation'] = nav
        logger.info(f"🧭 Найдено элементов навигации: {len(nav)}")
    
    async def scan_profile(self):
        """Сканирует информацию профиля"""
        profile = await self.page.evaluate('''
            () => {
                const result = {};
                const avatar = document.querySelector('[data-testid="UserAvatar-Container"] img');
                if (avatar) result.avatar = avatar.getAttribute('src') || '';
                
                const name = document.querySelector('[data-testid="UserName"]');
                if (name) result.name = name.textContent?.trim() || '';
                
                const bio = document.querySelector('[data-testid="UserDescription"]');
                if (bio) result.bio = bio.textContent?.trim() || '';
                
                const stats = document.querySelectorAll('[data-testid="UserProfileHeader_Items"] a');
                stats.forEach(el => {
                    const text = el.textContent?.trim() || '';
                    if (text.includes('Followers')) result.followers = text;
                    if (text.includes('Following')) result.following = text;
                });
                
                return result;
            }
        ''')
        self.results['profile'] = profile
        logger.info(f"👤 Профиль: {profile.get('name', 'Не найден')}")
    
    async def scan_selectors(self):
        """Собирает все основные селекторы для будущих функций"""
        selectors = await self.page.evaluate('''
            () => {
                const result = {
                    tweet_input: !!document.querySelector('[data-testid="tweetTextarea_0"]'),
                    tweet_button: !!document.querySelector('[data-testid="tweetButton"]'),
                    reply: !!document.querySelector('[data-testid="reply"]'),
                    retweet: !!document.querySelector('[data-testid="retweet"]'),
                    like: !!document.querySelector('[data-testid="like"]'),
                    bookmark: !!document.querySelector('[data-testid="bookmark"]'),
                    share: !!document.querySelector('[data-testid="share"]'),
                    search: !!document.querySelector('[data-testid="Search"]'),
                    dm: !!document.querySelector('[data-testid="dm"]'),
                    more: !!document.querySelector('[data-testid="more"]'),
                    profile: !!document.querySelector('[data-testid="profile"]'),
                    settings: !!document.querySelector('[data-testid="settings"]'),
                    logout: !!document.querySelector('[data-testid="logout"]')
                };
                return result;
            }
        ''')
        self.results['selectors'] = selectors
        
        # Сохраняем как готовые команды
        available_commands = []
        for key, exists in selectors.items():
            if exists:
                available_commands.append(f"/{key}")
        
        self.results['available_commands'] = available_commands
        logger.info(f"📋 Доступных функций: {len(available_commands)}")

# ========== КОМАНДЫ ТЕЛЕГРАМ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **X.com Scanner Bot**\n\n"
        "🚀 Полное сканирование X.com:\n"
        "/scan - сканировать текущую страницу\n"
        "/xlogin - войти в X.com\n"
        "/go <url> - открыть URL\n"
        "/report - показать отчет\n"
        "/export - экспортировать JSON\n"
        "/status - статус браузера\n"
        "/close - закрыть браузер\n\n"
        "📊 После /scan бот соберет:\n"
        "• Все кнопки и их testid\n"
        "• Все ссылки\n"
        "• Все формы\n"
        "• Все посты\n"
        "• Навигацию\n"
        "• Доступные функции"
    )

async def go(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /go https://x.com")
        return
    
    url = context.args[0]
    if not url.startswith('http'):
        url = 'https://' + url
    
    msg = await update.message.reply_text(f"⏳ Открываю {url}...")
    
    try:
        browser = await get_browser()
        await browser['page'].goto(url, wait_until='domcontentloaded', timeout=15000)
        await msg.edit_text(f"✅ Открыл: {url}")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def xlogin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Захожу в X.com...")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        await page.goto('https://x.com', wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(3)
        
        # Проверяем вход
        is_logged = await page.query_selector('[data-testid="tweetButton"]') is not None
        
        if is_logged:
            await msg.edit_text("✅ Успешный вход в X.com!")
        else:
            await msg.edit_text("⚠️ Вход не подтвержден. Попробуй /scan для проверки")
        
        # Делаем скриншот
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await update.message.reply_photo(photo=screenshot, caption="📸 Текущая страница")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полное сканирование X.com"""
    msg = await update.message.reply_text("🔍 Начинаю полное сканирование X.com...\n⏳ Это может занять 10-20 секунд")
    
    try:
        browser = await get_browser()
        page = browser['page']
        
        # Проверяем что на X.com
        if 'x.com' not in page.url:
            await msg.edit_text("❌ Сначала зайди на X.com через /xlogin")
            return
        
        # Создаем сканер
        scanner = XScanner(page)
        
        # Сканируем
        await msg.edit_text("📊 Сканирую страницу...\n"
                          "🔘 Кнопки...\n"
                          "🔗 Ссылки...\n"
                          "📝 Формы...\n"
                          "🏷️ TestID...\n"
                          "🐦 Посты...")
        
        results = await scanner.scan_full()
        
        # Сохраняем результаты
        global scan_results
        scan_results = results
        
        # Формируем отчет
        report = f"📊 **ОТЧЕТ О СКАНИРОВАНИИ**\n\n"
        report += f"📍 URL: {results['url'][:60]}\n"
        report += f"📌 Заголовок: {results['title'][:50]}\n\n"
        
        report += f"**📊 СТАТИСТИКА:**\n"
        report += f"🔘 Кнопок: {results['stats']['total_buttons']}\n"
        report += f"🔗 Ссылок: {results['stats']['total_links']}\n"
        report += f"📝 Форм: {results['stats']['total_forms']}\n"
        report += f"🏷️ TestID: {results['stats']['total_testids']}\n"
        report += f"🐦 Постов: {results['stats']['total_tweets']}\n\n"
        
        # Доступные функции
        if results.get('available_commands'):
            report += f"**✅ ДОСТУПНЫЕ ФУНКЦИИ:**\n"
            commands = results['available_commands'][:10]
            for cmd in commands:
                report += f"• `{cmd}`\n"
            if len(results['available_commands']) > 10:
                report += f"• ... и еще {len(results['available_commands']) - 10}\n"
            report += "\n"
        
        # Топ testid
        if results['testids']:
            report += f"**🏷️ ОСНОВНЫЕ TESTID:**\n"
            sorted_ids = sorted(results['testids'].items(), key=lambda x: x[1], reverse=True)[:5]
            for testid, count in sorted_ids:
                report += f"• `{testid}`: {count} шт.\n"
            report += "\n"
        
        # Последние посты
        if results['tweets']:
            report += f"**🐦 ПОСЛЕДНИЕ ПОСТЫ:**\n"
            for i, tweet in enumerate(results['tweets'][:3], 1):
                text = tweet['text'][:60].replace('\n', ' ')
                report += f"{i}. @{tweet['author']}: {text}...\n"
                report += f"   ❤️ {tweet['likes']}  🔁 {tweet['retweets']}\n"
        
        await msg.edit_text(report)
        
        # Отправляем JSON файл
        filename = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        await update.message.reply_document(
            document=open(filename, 'rb'),
            filename=filename,
            caption="📄 Полный отчет в JSON"
        )
        os.remove(filename)
        
        # Скриншот
        screenshot = await page.screenshot(type='jpeg', quality=80)
        await update.message.reply_photo(
            photo=screenshot,
            caption="📸 Скриншот страницы"
        )
        
        logger.info(f"✅ Сканирование завершено для user {update.effective_user.id}")
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        logger.error(f"Scan error: {e}")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает последний отчет"""
    global scan_results
    
    if not scan_results:
        await update.message.reply_text("❌ Нет данных. Сначала /scan")
        return
    
    # Форматируем отчет
    report = f"📊 **ОТЧЕТ ОТ {scan_results['timestamp']}**\n\n"
    report += f"📍 {scan_results['url'][:60]}\n"
    report += f"📌 {scan_results['title'][:50]}\n\n"
    
    stats = scan_results.get('stats', {})
    report += f"🔘 {stats.get('total_buttons', 0)} кнопок\n"
    report += f"🔗 {stats.get('total_links', 0)} ссылок\n"
    report += f"📝 {stats.get('total_forms', 0)} форм\n"
    report += f"🏷️ {stats.get('total_testids', 0)} testid\n"
    report += f"🐦 {stats.get('total_tweets', 0)} постов\n"
    
    await update.message.reply_text(report)

async def export_json(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Экспортирует данные в JSON"""
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
        caption="📄 Экспорт данных X.com"
    )
    os.remove(filename)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_data
    if browser_data:
        try:
            page = browser_data['page']
            url = page.url
            await update.message.reply_text(f"✅ Браузер активен\n📍 {url[:60]}")
        except:
            await update.message.reply_text("⚠️ Браузер открыт, но не отвечает")
    else:
        await update.message.reply_text("❌ Браузер закрыт")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_data
    if browser_data:
        try:
            await browser_data['browser'].close()
            await browser_data['playwright'].stop()
        except:
            pass
        browser_data = None
        await update.message.reply_text("✅ Браузер закрыт")
    else:
        await update.message.reply_text("❌ Браузер уже закрыт")

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("go", go))
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