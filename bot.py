import os
import logging
import threading
import asyncio
import random
import re
import time
from io import BytesIO
import requests
from flask import Flask, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from camoufox import AsyncCamoufox  # Замена playwright

# ============ НАСТРОЙКИ ============
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

MY_COOKIES = [
    {"name": "auth_token", "value": "09fe982487255e707f7a9b3d380ea429421adae3", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "18f7448391062aaaa323ea38f4fd129f5f682f09ec0989f899ebc4ddaa4d7bf7de0e0c359240145428b7cc1d410adbc5565fa9bbe2c4380b5341327ea3c53f03a89fcb12ee617d0fea848882ae6ff281", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
]

user_sessions = {}

app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return jsonify({"status": "Бот работает!"})

@app_flask.route('/health')
def health():
    return jsonify({"status": "ok"})

def run_flask():
    port = int(os.getenv("PORT", 8080))
    app_flask.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def keep_alive():
    while True:
        try:
            requests.get("https://api.telegram.org")
            print("💓 Keep-alive ping")
        except:
            pass
        time.sleep(1200)

# ============ ЭМУЛЯЦИЯ ЧЕЛОВЕКА ============
async def human_sleep(min_sec=0.3, max_sec=1.5):
    await asyncio.sleep(random.uniform(min_sec, max_sec))

async def human_move(page, x, y, steps=12):
    try:
        current = await page.evaluate("""
            () => ({
                x: window.scrollX + window.innerWidth / 2,
                y: window.scrollY + window.innerHeight / 2
            })
        """)
        for i in range(steps):
            progress = (i + 1) / steps
            ease = 1 - (1 - progress) ** 3
            noise_x = random.randint(-3, 3)
            noise_y = random.randint(-3, 3)
            target_x = current["x"] + (x - current["x"]) * ease + noise_x
            target_y = current["y"] + (y - current["y"]) * ease + noise_y
            await page.mouse.move(target_x, target_y)
            await asyncio.sleep(random.uniform(0.02, 0.08))
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.05, 0.2))
        return True
    except:
        return False

async def human_click(page, x, y, button="left"):
    try:
        await human_move(page, x, y, steps=10)
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.mouse.down(button=button)
        await asyncio.sleep(random.uniform(0.03, 0.12))
        await page.mouse.up(button=button)
        await asyncio.sleep(random.uniform(0.1, 0.3))
        return True
    except:
        return False

async def human_scroll(page, amount, steps=4):
    try:
        for i in range(steps):
            progress = (i + 1) / steps
            eased = 1 - (1 - progress) ** 2
            scroll_amount = int(amount * eased * 0.6 + random.randint(-10, 10))
            await page.mouse.wheel(0, scroll_amount)
            await asyncio.sleep(random.uniform(0.1, 0.4))
        return True
    except:
        return False

async def take_screenshot(page) -> bytes:
    try:
        return await page.screenshot(type="png")
    except:
        return b""

def escape_markdown(text):
    if not text:
        return ''
    return re.sub(r'([_*\[\]()~>#+=|{}.!-])', r'\\\1', text)

# ============ CAMOUFOX БРАУЗЕР ============
async def get_browser(user_id: int = None):
    """Создает браузер Camoufox с уникальным профилем для каждого пользователя"""
    
    # Директория для профиля (сохраняет куки/сессию)
    profile_dir = f"/data/profile_{user_id}" if user_id else None
    
    # Прокси из переменных окружения (опционально)
    proxy = os.getenv("PROXY_URL")
    
    # Запускаем Camoufox
    browser = await AsyncCamoufox(
        headless="virtual",  # Режим для сервера без GUI
        profile_dir=profile_dir,
        proxy=proxy,
        geoip=bool(proxy),  # Автоподстройка гео под прокси
    ).__aenter__()
    
    # Создаем контекст с реалистичным отпечатком (автоматически)
    context = await browser.new_context()
    
    # Добавляем ваши куки
    if MY_COOKIES:
        await context.add_cookies(MY_COOKIES)
    
    page = await context.new_page()
    
    # Дополнительная маскировка (хотя Camoufox уже все маскирует)
    await page.add_init_script("""
        console.log('✅ Дополнительная маскировка от бота');
        
        // Удаление следов автоматизации (на всякий случай)
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        delete Object.getPrototypeOf(navigator).webdriver;
        
        // Chrome объект
        if (!window.chrome) {
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: { isInstalled: false }
            };
        }
        
        // Плагины
        if (!navigator.plugins || navigator.plugins.length === 0) {
            const plugins = [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                { name: 'Native Client', filename: 'internal-nacl-plugin' }
            ];
            plugins.length = 3;
            plugins.item = (i) => plugins[i] || null;
            plugins.namedItem = (name) => plugins.find(p => p.name === name) || null;
            Object.defineProperty(navigator, 'plugins', { get: () => plugins });
        }
    """)
    
    return page, browser, context

async def get_user_browser(user_id: int):
    """Получает или создает браузер для пользователя"""
    if user_id not in user_sessions:
        page, browser, context = await get_browser(user_id)
        user_sessions[user_id] = {
            "page": page,
            "browser": browser,
            "context": context
        }
        # Открываем пустую страницу для инициализации
        await page.goto("about:blank")
    return user_sessions[user_id]

async def close_user_browser(user_id: int):
    """Закрывает браузер пользователя"""
    if user_id in user_sessions:
        try:
            browser = user_sessions[user_id]["browser"]
            await browser.close()
        except:
            pass
        del user_sessions[user_id]

# ============ КОМАНДЫ ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 **БОТ**\n\n"
        "/browser — Открыть браузер\n"
        "/x — Открыть X.com\n"
        "/screenshot — Скриншот\n"
        "/tweets — 3 твита\n"
        "/status — Статус\n"
        "/close — Закрыть",
        parse_mode="Markdown"
    )

async def browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await update.message.reply_text("🌐 Открываю браузер Camoufox...")
    await get_user_browser(user_id)
    await update.message.reply_text("✅ Браузер готов!")

async def x_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала /browser")
        return
    
    await update.message.reply_text("🐦 Открываю X.com...")
    page = user_sessions[user_id]["page"]
    
    try:
        await page.goto("https://x.com", timeout=30000)
        await asyncio.sleep(3)
        
        # Проверяем ошибку
        error_text = await page.text_content("body")
        if error_text and "Something went wrong" in error_text:
            await update.message.reply_text(
                "⚠️ **X.com видит бота!**\n\n"
                "Попробуй:\n"
                "1. /browser — перезапустить браузер\n"
                "2. /x — ещё раз\n"
                "3. Использовать прокси (PROXY_URL)\n\n"
                "Если не поможет — попробуй обновить куки."
            )
            return
        
        screenshot = await take_screenshot(page)
        if screenshot and len(screenshot) > 1000:
            await update.message.reply_photo(photo=BytesIO(screenshot), caption="✅ X.com открыт!")
        else:
            await update.message.reply_text("✅ X.com открыт!")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала /browser")
        return
    
    page = user_sessions[user_id]["page"]
    screenshot = await take_screenshot(page)
    
    if screenshot and len(screenshot) > 1000:
        await update.message.reply_photo(photo=BytesIO(screenshot), caption="📸 Скриншот")
    else:
        await update.message.reply_text("❌ Не удалось")

async def tweets_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала /browser")
        return
    
    await update.message.reply_text("📡 Собираю твиты...")
    page = user_sessions[user_id]["page"]
    
    try:
        await page.goto("https://x.com", timeout=30000)
        await asyncio.sleep(4)
        
        for _ in range(2):
            await human_scroll(page, 600)
            await asyncio.sleep(1)
        
        tweets = await page.evaluate("""
            () => {
                const posts = [];
                const articles = document.querySelectorAll('[data-testid="tweet"], article');
                articles.forEach((article, index) => {
                    if (index >= 3) return;
                    try {
                        const nameEl = article.querySelector('[data-testid="User-Name"]');
                        let name = 'Неизвестно', username = '';
                        if (nameEl) {
                            const spans = nameEl.querySelectorAll('span');
                            if (spans.length > 0) name = spans[0]?.textContent || 'Неизвестно';
                            if (spans.length > 1) username = spans[1]?.textContent?.replace('@', '') || '';
                        }
                        const textEl = article.querySelector('[data-testid="tweetText"]');
                        const text = textEl ? textEl.textContent : '';
                        const timeEl = article.querySelector('time');
                        const time = timeEl ? timeEl.textContent : '';
                        const linkEl = article.querySelector('a[href*="/status/"]');
                        let link = '';
                        if (linkEl) {
                            const href = linkEl.getAttribute('href');
                            if (href) link = 'https://x.com' + href;
                        }
                        if (text || link) {
                            posts.push({ name, username, text, time, link });
                        }
                    } catch(e) {}
                });
                return posts;
            }
        """)
        
        if tweets and len(tweets) > 0:
            for i, tweet in enumerate(tweets, 1):
                msg = (
                    f"📌 **Твит {i}**\n\n"
                    f"👤 **{escape_markdown(tweet['name'])}**\n"
                    f"🔹 @{escape_markdown(tweet['username'])}\n"
                    f"🕐 {escape_markdown(tweet['time'])}\n\n"
                    f"📝 {escape_markdown(tweet['text'][:500])}{'...' if len(tweet['text']) > 500 else ''}\n\n"
                    f"🔗 {escape_markdown(tweet['link'])}"
                )
                await update.message.reply_text(msg, parse_mode="Markdown")
                await asyncio.sleep(0.5)
            await update.message.reply_text("✅ Готово!")
        else:
            await update.message.reply_text("❌ Посты не найдены")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Браузер не открыт")
        return
    
    page = user_sessions[user_id]["page"]
    url = page.url
    cookies = await page.context.cookies()
    has_cookie = any(c['name'] == 'auth_token' for c in cookies)
    
    if "x.com" in url and has_cookie:
        login_status = "✅ Вошли"
    elif "x.com" in url and not has_cookie:
        login_status = "❌ Не вошли"
    else:
        login_status = "⚠️ Не на X.com"
    
    text = (
        f"🌐 URL: {url[:80]}\n"
        f"🍪 Куки: {'✅ Есть' if has_cookie else '❌ Нет'}\n"
        f"📱 X.com: {login_status}\n"
        f"🦊 Браузер: Camoufox"
    )
    
    await update.message.reply_text(text)

async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await close_user_browser(user_id)
    await update.message.reply_text("❌ Браузер закрыт")

# ============ ЗАПУСК ============
def main():
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    
    bot_app = Application.builder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("browser", browser_command))
    bot_app.add_handler(CommandHandler("x", x_command))
    bot_app.add_handler(CommandHandler("screenshot", screenshot_command))
    bot_app.add_handler(CommandHandler("tweets", tweets_command))
    bot_app.add_handler(CommandHandler("status", status_command))
    bot_app.add_handler(CommandHandler("close", close_command))
    
    print("✅ Бот запущен на Camoufox!")
    bot_app.run_polling()

if __name__ == "__main__":
    main()