import os
import logging
import asyncio
import base64
from itertools import islice
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.extractor import ExtractionModel, Field

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

# ==================== МОДЕЛИ ====================

class Quote(ExtractionModel):
    text: str = Field(selector='.text')
    author: str = Field(selector='.author')
    tags: str = Field(selector='.tag')

class Tweet(ExtractionModel):
    text: str = Field(selector='div[data-testid="tweetText"]', default="[текст не найден]")
    author: str = Field(selector='div[data-testid="User-Name"] span', default="[автор не найден]")
    timestamp: str = Field(selector='time', default="[время не указано]")

CHROME_PATH = '/usr/bin/chromium'

X_COOKIES = [
    {"name": "__cuid", "value": "55d2d7c5-4888-430a-b024-dd785da46ef4", "domain": ".x.com", "path": "/"},
    {"name": "lang", "value": "ru", "domain": ".x.com", "path": "/"},
    {"name": "dnt", "value": "1", "domain": ".x.com", "path": "/"},
    {"name": "guest_id", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_marketing", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_ads", "value": "v1%3A178267838599411411", "domain": ".x.com", "path": "/"},
    {"name": "personalization_id", "value": "\"v1_DKrxLZAC902dMFdd1QrVYg==\"", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
    {"name": "auth_token", "value": "c9d83e923e1ad6cf67d19a0bc4f9877a49087936", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "39ee0cdf3c0179fb8c50265001cd49e64d652fd3f647e9f091b372641a1d444a1842958c253fe1621a04794de13817dec713e305ed75866c00ecc2a7a0aec112940c06283ca7745b106c4e71a863e3eb", "domain": ".x.com", "path": "/"},
    {"name": "__cf_bm", "value": "0lyNYlKnbjXejqIk_blw2x20TfMRtW3SWJ_jmpay.t4-1783123617.0158947-1.0.1.1-1rnugK6C5Aw5r.126FQ3rJYZTCG2WhtPATFYO5Ip0QukW40cCR0qDNfacg6VRv3vRh3w.4Un_NQ6hOnxQfvhm68Grg1hZiLbF6HAyxvxzmS06Q8AzQkKu_i248B5sxj7", "domain": ".x.com", "path": "/"}
]

user_browsers = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = (
        "🤖 *Исследователь X.com*\n\n"
        "🔐 *Авторизация*\n"
        "/login — Войти в X.com\n\n"
        "🔍 *Исследование*\n"
        "/explore_page — Полное исследование страницы\n"
        "/explore_selector <селектор> — Детально исследовать элемент\n\n"
        "⚡ *JavaScript*\n"
        "/eval <js> — Выполнить JavaScript"
    )
    await update.message.reply_text(menu, parse_mode='Markdown')

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        await update.message.reply_text("🔐 Выполняю вход на X.com...")
        
        options = ChromiumOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.binary_location = CHROME_PATH
        
        browser = Chrome(options=options)
        tab = await browser.start()
        
        await tab.go_to('https://x.com')
        await asyncio.sleep(2)
        
        await tab.set_cookies(X_COOKIES)
        await asyncio.sleep(1)
        
        await tab.refresh()
        await asyncio.sleep(5)
        
        user_browsers[user_id] = (browser, tab)
        
        await update.message.reply_text("✅ Вход выполнен успешно!")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка входа: {str(e)[:300]}")

async def explore_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полное исследование страницы с сохранением в файл"""
    user_id = update.effective_user.id
    username = update.effective_user.username or f"user_{user_id}"
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        _, tab = user_browsers[user_id]
        
        await update.message.reply_text("🔍 Исследую страницу...")
        
        url = await tab.current_url
        title = await tab.title
        
        all_testids = await tab.execute_script("""
            (function() {
                const ids = new Set();
                document.querySelectorAll('[data-testid]').forEach(el => {
                    ids.add(el.dataset.testid);
                });
                return Array.from(ids);
            })()
        """)
        
        main_selectors = [
            ('Твиты', 'article[data-testid="tweet"]'),
            ('Текст твита', 'div[data-testid="tweetText"]'),
            ('Автор', 'div[data-testid="User-Name"]'),
            ('Лайки', 'button[data-testid="like"]'),
            ('Ретвиты', 'button[data-testid="retweet"]'),
            ('Ответы', 'button[data-testid="reply"]'),
            ('Фото', 'div[data-testid="tweetPhoto"]'),
            ('Поиск', 'input[data-testid="SearchBox_Search_Input"]'),
            ('Главная', 'a[data-testid="AppTabBar_Home_Link"]'),
            ('Explore', 'a[data-testid="AppTabBar_Explore_Link"]'),
            ('Уведомления', 'a[data-testid="AppTabBar_Notifications_Link"]'),
            ('Сообщения', 'a[data-testid="AppTabBar_Messages_Link"]'),
            ('Профиль', 'a[data-testid="AppTabBar_Profile_Link"]'),
            ('Подписчики', 'a[href*="/followers"]'),
            ('Подписки', 'a[href*="/following"]'),
        ]
        
        elements_info = {}
        for name, selector in main_selectors:
            try:
                count = await tab.execute_script(f"document.querySelectorAll('{selector}').length")
                if count > 0:
                    sample = await tab.execute_script(f"""
                        (function() {{
                            const el = document.querySelector('{selector}');
                            if (!el) return '';
                            return el.innerText.substring(0, 100) || '';
                        }})()
                    """)
                    elements_info[name] = {
                        'selector': selector,
                        'count': count,
                        'sample': sample.strip() if sample else ''
                    }
            except:
                pass
        
        tweet_sample = await tab.execute_script("""
            (function() {
                const tweet = document.querySelector('article[data-testid="tweet"]');
                if (!tweet) return null;
                const text = tweet.querySelector('div[data-testid="tweetText"]')?.innerText || '';
                const author = tweet.querySelector('div[data-testid="User-Name"] span')?.innerText || '';
                return { text: text.substring(0, 300), author };
            })()
        """)
        
        # ✅ ИСПОЛЬЗУЕМ islice ДЛЯ БЕЗОПАСНОГО СРЕЗА
        images = await tab.find(tag_name='img', src_contains='media', find_all=True)
        image_urls = []
        for img in islice(images, 10):
            src = await img.get_attribute('src')
            if src:
                image_urls.append(src)
        
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append("🔍 ПОЛНОЕ ИССЛЕДОВАНИЕ СТРАНИЦЫ")
        report_lines.append("=" * 60)
        report_lines.append(f"\n📍 URL: {url}")
        report_lines.append(f"📄 Title: {title}")
        report_lines.append(f"🕐 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        report_lines.append("\n" + "=" * 60)
        report_lines.append("📊 НАЙДЕННЫЕ ЭЛЕМЕНТЫ")
        report_lines.append("=" * 60)
        
        for name, data in elements_info.items():
            report_lines.append(f"\n• {name}:")
            report_lines.append(f"  Селектор: {data['selector']}")
            report_lines.append(f"  Количество: {data['count']}")
            if data.get('sample'):
                report_lines.append(f"  Пример: {data['sample'][:100]}...")
        
        report_lines.append("\n" + "=" * 60)
        report_lines.append("📋 ВСЕ DATA-TESTID")
        report_lines.append("=" * 60)
        
        for i, tid in enumerate(all_testids, 1):
            report_lines.append(f"  {i}. {tid}")
        
        if tweet_sample:
            report_lines.append("\n" + "=" * 60)
            report_lines.append("📝 ПРИМЕР ТВИТА")
            report_lines.append("=" * 60)
            report_lines.append(f"\nТекст: {tweet_sample.get('text', '')}")
            report_lines.append(f"Автор: {tweet_sample.get('author', '')}")
        
        if image_urls:
            report_lines.append("\n" + "=" * 60)
            report_lines.append("🖼️ НАЙДЕННЫЕ ФОТО")
            report_lines.append("=" * 60)
            for i, url in enumerate(image_urls, 1):
                report_lines.append(f"  {i}. {url}")
        
        report_lines.append("\n" + "=" * 60)
        report_lines.append("💡 ИНСТРУКЦИЯ")
        report_lines.append("=" * 60)
        report_lines.append("\n  • /explore_selector <селектор> — детально")
        report_lines.append("  • /eval <js> — выполнить JavaScript")
        
        report_text = '\n'.join(report_lines)
        
        filename = f"explore_{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report_text)
        
        short_reply = f"🔍 *Исследование страницы*\n\n"
        short_reply += f"📍 URL: {url}\n"
        short_reply += f"📄 Title: {title}\n\n"
        
        if elements_info:
            short_reply += "📊 *Найдено элементов:*\n"
            for name, data in list(elements_info.items())[:10]:
                short_reply += f"  • {name}: {data['count']} шт.\n"
            if len(elements_info) > 10:
                short_reply += f"  ... и ещё {len(elements_info) - 10}\n"
        
        if all_testids:
            short_reply += f"\n📋 *Data-testid: {len(all_testids)} шт.*\n"
            for tid in all_testids[:10]:
                short_reply += f"  • `{tid}`\n"
            if len(all_testids) > 10:
                short_reply += f"  ... и ещё {len(all_testids) - 10}\n"
        
        short_reply += f"\n📁 *Файл с полным логом:* `{filename}`"
        
        await update.message.reply_text(short_reply, parse_mode='Markdown')
        
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"📁 Полный лог исследования\n📍 {url}"
            )
        
        screenshot_base64 = await asyncio.wait_for(
            tab.take_screenshot(as_base64=True),
            timeout=30.0
        )
        screenshot_bytes = base64.b64decode(screenshot_base64)
        await update.message.reply_photo(
            photo=screenshot_bytes,
            caption=f"🖼️ Скриншот страницы"
        )
        
        try:
            os.remove(filename)
        except:
            pass
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def explore_selector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детальное исследование конкретного элемента"""
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи селектор\nПример: /explore_selector article[data-testid=\"tweet\"]"
        )
        return
    
    selector = ' '.join(context.args)
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала выполни /login")
            return
        
        _, tab = user_browsers[user_id]
        
        exists = await tab.execute_script(f"!!document.querySelector('{selector}')")
        if not exists:
            await update.message.reply_text(f"❌ Элемент не найден: {selector}")
            return
        
        testids = await tab.execute_script(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return [];
                const ids = [];
                el.querySelectorAll('[data-testid]').forEach(el => {{
                    const id = el.dataset.testid;
                    if (!ids.includes(id)) ids.push(id);
                }});
                return ids;
            }})()
        """)
        
        text = await tab.execute_script(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return '';
                return el.innerText.substring(0, 500);
            }})()
        """)
        
        classes = await tab.execute_script(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (!el) return '';
                return el.className || '';
            }})()
        """)
        
        reply = f"🔍 *Исследование селектора:* `{selector}`\n\n"
        
        if classes:
            reply += f"📦 *Классы:* `{classes}`\n\n"
        
        if testids and len(testids) > 0:
            reply += "📋 *Найденные data-testid:*\n"
            for tid in testids[:20]:
                reply += f"  • `{tid}`\n"
            if len(testids) > 20:
                reply += f"  ... и ещё {len(testids) - 20}\n"
        
        if text:
            reply += f"\n📝 *Текст:*\n{text[:300]}..."
        
        await update.message.reply_text(reply, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def evaluate_js(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи JS код\nПример: /eval document.title"
        )
        return
    
    js_code = ' '.join(context.args)
    user_id = update.effective_user.id
    
    try:
        if user_id not in user_browsers:
            await update.message.reply_text("❌ Сначала открой сайт командой /go или /login")
            return
        
        _, tab = user_browsers[user_id]
        result = await tab.execute_script(js_code)
        await update.message.reply_text(f"✅ Результат:\n\n{str(result)[:500]}")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:300]}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("explore_page", explore_page))
    application.add_handler(CommandHandler("explore_selector", explore_selector))
    application.add_handler(CommandHandler("eval", evaluate_js))
    
    application.add_error_handler(error_handler)
    
    if os.path.exists(CHROME_PATH):
        logger.info(f"✅ Браузер найден: {CHROME_PATH}")
    else:
        logger.error(f"❌ Браузер не найден: {CHROME_PATH}")
    
    logger.info("🚀 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()