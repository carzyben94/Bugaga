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
from cloakbrowser import launch

# ============ НАСТРОЙКИ ============
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

MY_COOKIES = [
    {"name": "auth_token", "value": "09fe982487255e707f7a9b3d380ea429421adae3", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "18f7448391062aaaa323ea38f4fd129f5f682f09ec0989f899ebc4ddaa4d7bf7de0e0c359240145428b7cc1d410adbc5565fa9bbe2c4380b5341327ea3c53f03a89fcb12ee617d0fea848882ae6ff281", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D2067347503503052800", "domain": ".x.com", "path": "/"},
]

user_sessions = {}
user_locks = {}

app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return jsonify({"status": "Бот работает!", "sessions": len(user_sessions)})

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

# ============ ЗАПУСК БРАУЗЕРА ============
def create_browser_sync(user_id, status_queue):
    """Создает браузер в синхронном режиме"""
    try:
        logging.info(f"[{user_id}] Начинаю запуск браузера")
        status_queue.append("🚀 Запускаю CloakBrowser...")
        status_queue.append("⏳ Первый запуск: скачивание ~200 МБ (1-2 минуты)")
        
        browser = launch(headless=True, humanize=True)
        logging.info(f"[{user_id}] Браузер запущен")
        status_queue.append("✅ Браузер запущен!")
        
        context = browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        logging.info(f"[{user_id}] Контекст создан")
        status_queue.append("✅ Контекст создан!")
        
        if MY_COOKIES:
            context.add_cookies(MY_COOKIES)
            logging.info(f"[{user_id}] Добавлено {len(MY_COOKIES)} куки")
            status_queue.append(f"🍪 Добавлено {len(MY_COOKIES)} куки")
        
        page = context.new_page()
        logging.info(f"[{user_id}] Страница создана")
        status_queue.append("✅ Страница создана!")
        
        # Открываем пустую страницу
        page.goto("about:blank")
        logging.info(f"[{user_id}] Браузер полностью готов")
        status_queue.append("✅ Браузер полностью готов!")
        
        return {
            'browser': browser,
            'context': context,
            'page': page
        }
    except Exception as e:
        logging.error(f"[{user_id}] Ошибка: {e}")
        status_queue.append(f"❌ Ошибка: {str(e)[:200]}")
        raise

async def get_user_browser(user_id, update=None):
    """Получает или создает браузер для пользователя"""
    if user_id not in user_locks:
        user_locks[user_id] = asyncio.Lock()
    
    async with user_locks[user_id]:
        # Проверяем, есть ли уже сессия
        if user_id in user_sessions:
            logging.info(f"[{user_id}] Браузер уже существует")
            if update:
                await update.message.reply_text("✅ Браузер уже запущен")
            return user_sessions[user_id]
        
        logging.info(f"[{user_id}] Создаю новый браузер")
        status_queue = []
        
        if update:
            await update.message.reply_text("🌐 **Открываю браузер CloakBrowser...**")
        
        try:
            # Запускаем браузер в потоке
            result = await asyncio.to_thread(create_browser_sync, user_id, status_queue)
            
            # Сохраняем сессию
            user_sessions[user_id] = result
            logging.info(f"[{user_id}] Браузер сохранен в сессию. Всего сессий: {len(user_sessions)}")
            
            # Отправляем статусы
            if update:
                for msg in status_queue:
                    if not msg.startswith('⏳'):
                        await update.message.reply_text(f"🔄 {msg}")
                await update.message.reply_text("✅ **Браузер готов к работе!**")
            
            return result
            
        except Exception as e:
            logging.error(f"[{user_id}] Критическая ошибка: {e}")
            if update:
                await update.message.reply_text(f"❌ **Ошибка:** {str(e)[:200]}")
            raise

async def close_user_browser(user_id):
    if user_id in user_sessions:
        try:
            await asyncio.to_thread(user_sessions[user_id]['browser'].close)
            logging.info(f"[{user_id}] Браузер закрыт")
        except Exception as e:
            logging.error(f"[{user_id}] Ошибка при закрытии: {e}")
        del user_sessions[user_id]
        logging.info(f"[{user_id}] Сессия удалена. Осталось сессий: {len(user_sessions)}")

# ============ КОМАНДЫ ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **БОТ на CloakBrowser**\n\n"
        "/browser — Открыть браузер\n"
        "/x — Открыть X.com\n"
        "/screenshot — Скриншот\n"
        "/tweets — 3 твита\n"
        "/status — Статус браузера\n"
        "/close — Закрыть браузер",
        parse_mode="Markdown"
    )

async def browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /browser - запускает браузер"""
    user_id = update.effective_user.id
    logging.info(f"[{user_id}] Команда /browser")
    try:
        await get_user_browser(user_id, update)
    except Exception as e:
        logging.error(f"[{user_id}] Ошибка в /browser: {e}")
        await update.message.reply_text(f"❌ Критическая ошибка: {str(e)[:200]}")

async def x_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /x - открывает X.com"""
    user_id = update.effective_user.id
    logging.info(f"[{user_id}] Команда /x")
    
    # Проверяем, есть ли браузер
    if user_id not in user_sessions:
        logging.warning(f"[{user_id}] Браузер не найден")
        await update.message.reply_text("⚠️ **Браузер не открыт!**\n\nСначала выполните `/browser`", parse_mode="Markdown")
        return
    
    await update.message.reply_text("🐦 Открываю X.com...")
    page = user_sessions[user_id]['page']
    
    try:
        # Пробуем открыть X.com
        await page.goto("https://x.com", timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        current_url = page.url
        logging.info(f"[{user_id}] Текущий URL: {current_url}")
        
        if "x.com" not in current_url and "twitter.com" not in current_url:
            await update.message.reply_text(
                f"⚠️ Перенаправлено на: {current_url[:50]}\n"
                "Попробуйте обновить куки или использовать прокси."
            )
            return
        
        screenshot = await take_screenshot(page)
        if screenshot and len(screenshot) > 1000:
            await update.message.reply_photo(
                photo=BytesIO(screenshot), 
                caption=f"✅ X.com открыт!"
            )
        else:
            await update.message.reply_text(f"✅ X.com открыт!")
            
    except Exception as e:
        error_msg = str(e)[:300]
        logging.error(f"[{user_id}] Ошибка в /x: {e}")
        await update.message.reply_text(
            f"❌ **Ошибка при открытии X.com:**\n\n"
            f"`{error_msg}`\n\n"
            "Попробуйте:\n"
            "1. `/close` — закрыть браузер\n"
            "2. `/browser` — перезапустить\n"
            "3. `/x` — попробовать снова",
            parse_mode="Markdown"
        )

async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала /browser")
        return
    
    page = user_sessions[user_id]['page']
    screenshot = await take_screenshot(page)
    
    if screenshot and len(screenshot) > 1000:
        await update.message.reply_photo(photo=BytesIO(screenshot), caption="📸 Скриншот")
    else:
        await update.message.reply_text("❌ Не удалось сделать скриншот")

async def tweets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала /browser")
        return
    
    await update.message.reply_text("📡 Собираю твиты...")
    page = user_sessions[user_id]['page']
    
    try:
        await page.goto("https://x.com", timeout=30000, wait_until="domcontentloaded")
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
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status - показывает статус браузера"""
    user_id = update.effective_user.id
    logging.info(f"[{user_id}] Команда /status")
    
    if user_id not in user_sessions:
        await update.message.reply_text(
            "⚠️ **Браузер не открыт**\n\n"
            f"Всего сессий в памяти: {len(user_sessions)}\n"
            "Выполните `/browser` для запуска",
            parse_mode="Markdown"
        )
        return
    
    page = user_sessions[user_id]['page']
    url = page.url
    cookies = await page.context.cookies()
    has_cookie = any(c['name'] == 'auth_token' for c in cookies)
    
    text = (
        f"📊 **Статус браузера**\n\n"
        f"🌐 URL: {url[:80]}\n"
        f"🍪 Куки: {'✅ Есть' if has_cookie else '❌ Нет'}\n"
        f"📱 На X.com: {'✅ Да' if 'x.com' in url else '❌ Нет'}\n"
        f"🦊 Браузер: CloakBrowser\n"
        f"📌 Сессий в памяти: {len(user_sessions)}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    print("✅ Бот запущен на CloakBrowser!")
    print(f"📊 Количество сессий: {len(user_sessions)}")
    bot_app.run_polling()

if __name__ == "__main__":
    main()