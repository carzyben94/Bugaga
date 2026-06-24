import os
import logging
import threading
import time
import asyncio
import random
import json
from io import BytesIO
import requests
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from playwright.async_api import async_playwright

# ============ НАСТРОЙКИ ============
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")

# Хранилища
user_sessions = {}
cursor_positions = {}

# ============ FLASK ============
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return jsonify({"status": "Бот работает!"})

@app_flask.route('/health')
def health():
    return jsonify({"status": "ok"})

def keep_alive():
    while True:
        try:
            requests.get("https://api.telegram.org")
            print("💓 Keep-alive ping")
        except:
            pass
        time.sleep(1200)

# ============ БРАУЗЕР ============
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
VIEWPORT = {"width": 1366, "height": 768}

async def get_browser_page():
    playwright = await async_playwright().start()
    
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--disable-gpu',
        ]
    )
    
    context = await browser.new_context(
        viewport=VIEWPORT,
        user_agent=USER_AGENT,
        locale="ru-RU",
        timezone_id="Europe/Moscow",
        java_script_enabled=True,
    )
    
    page = await context.new_page()
    
    # Базовая маскировка
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['ru-RU', 'ru', 'en-US', 'en'] });
        window.chrome = { runtime: {} };
    """)
    
    return page, browser, context

async def get_user_browser(user_id: int):
    if user_id not in user_sessions:
        page, browser, context = await get_browser_page()
        user_sessions[user_id] = {
            "page": page,
            "browser": browser,
            "context": context,
            "current_url": "about:blank"
        }
        await page.goto("about:blank")
        cursor_positions[user_id] = {"x": VIEWPORT["width"] // 2, "y": VIEWPORT["height"] // 2}
        return user_sessions[user_id]
    return user_sessions[user_id]

async def close_user_browser(user_id: int):
    if user_id in user_sessions:
        await user_sessions[user_id]["browser"].close()
        del user_sessions[user_id]
        if user_id in cursor_positions:
            del cursor_positions[user_id]

async def goto_url(page, url: str):
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        print(f"✅ {url} загружен")
        return True
    except Exception as e:
        print(f"❌ Ошибка загрузки {url}: {e}")
        raise e

# ============ ДЕЙСТВИЯ ============
async def human_screenshot(page, x: int, y: int) -> bytes:
    try:
        screenshot = await page.screenshot(full_page=False, type="png")
        return screenshot
    except Exception as e:
        print(f"Ошибка скриншота: {e}")
        return b""

# ============ КОМАНДА /START ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 **КОМАНДЫ БОТА**\n\n"
        "🌐 **БРАУЗЕР**\n"
        "/browser — Открыть браузер\n"
        "/close — Закрыть браузер\n"
        "/go url — Перейти на сайт\n"
        "/status — Статус\n"
        "/screenshot — Скриншот\n\n"
        "🐦 **X**\n"
        "/xlogin — Войти в X.com\n"
        "/xhome — Главная X.com\n"
        "/xprofile — Профиль\n"
        "/xtrends — Тренды\n\n"
        "📸 **ИНФО**\n"
        "/status — Статус браузера",
        parse_mode="Markdown"
    )

# ============ /BROWSER ============
async def browser_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await update.message.reply_text("🌐 Открываю браузер...")
    try:
        await get_user_browser(user_id)
        session = user_sessions[user_id]
        context.user_data['page'] = session["page"]
        await update.message.reply_text("✅ Браузер готов!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ /CLOSE ============
async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await close_user_browser(user_id)
    if 'page' in context.user_data:
        del context.user_data['page']
    await update.message.reply_text("❌ Браузер закрыт")

# ============ /GO ============
async def go_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите URL: /go google.com")
        return
    url = args[0]
    if not url.startswith("http"):
        url = "https://" + url
    try:
        session = await get_user_browser(user_id)
        page = session["page"]
        await update.message.reply_text(f"🌐 Перехожу на {url}...")
        await goto_url(page, url)
        session["current_url"] = url
        screenshot = await human_screenshot(page, 100, 100)
        await update.message.reply_photo(photo=screenshot, caption=f"✅ {url}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ /STATUS ============
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Браузер не открыт. Используй: /browser")
        return
    session = user_sessions[user_id]
    page = session["page"]
    url = page.url
    cookies = await page.context.cookies()
    has_cookie = any(c['name'] in ['auth_token', 'ct0', 'twid'] for c in cookies)
    status_text = f"📊 **Статус**\n\n"
    status_text += f"🌐 URL: {url[:60]}\n"
    status_text += f"🍪 Куки: {'✅ Есть' if has_cookie else '❌ Нет'}\n"
    if "x.com" in url:
        status_text += f"📱 X.com - {'✅ Вошли' if has_cookie else '❌ Не вошли'}\n"
    screenshot = await human_screenshot(page, 100, 100)
    await update.message.reply_photo(photo=screenshot, caption=status_text)

# ============ /SCREENSHOT ============
async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    try:
        session = user_sessions[user_id]
        page = session["page"]
        screenshot = await human_screenshot(page, 100, 100)
        await update.message.reply_photo(photo=screenshot, caption="📸 Скриншот")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ /XLOGIN ============
async def xlogin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await update.message.reply_text("🐦 Открываю X.com...")
    try:
        await get_user_browser(user_id)
        session = user_sessions[user_id]
        page = session["page"]
        context.user_data['page'] = page
        
        await goto_url(page, "https://x.com")
        session["current_url"] = "https://x.com"
        await page.wait_for_timeout(3000)
        
        screenshot = await human_screenshot(page, 100, 100)
        await update.message.reply_photo(
            photo=screenshot,
            caption="✅ X.com открыт! Используй /status для проверки входа"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ /XHOME ============
async def xhome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    try:
        session = user_sessions[user_id]
        page = session["page"]
        await goto_url(page, "https://x.com")
        await page.wait_for_timeout(3000)
        screenshot = await human_screenshot(page, 100, 100)
        await update.message.reply_photo(photo=screenshot, caption="🏠 Главная X.com")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ /XPROFILE ============
async def xprofile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    try:
        session = user_sessions[user_id]
        page = session["page"]
        await goto_url(page, "https://x.com")
        await page.wait_for_timeout(3000)
        
        profile = await page.evaluate("""
            () => {
                const data = { name: '', username: '', bio: '', followers: 0, following: 0 };
                try {
                    const nameEl = document.querySelector('[data-testid="UserName"]');
                    if (nameEl) {
                        const spans = nameEl.querySelectorAll('span');
                        if (spans.length > 0) data.name = spans[0].textContent;
                        if (spans.length > 1) data.username = spans[1].textContent.replace('@', '');
                    }
                    const bioEl = document.querySelector('[data-testid="UserDescription"]');
                    if (bioEl) data.bio = bioEl.textContent;
                } catch(e) {}
                return data;
            }
        """)
        
        text = f"👤 **{profile.get('name', 'Неизвестно')}**\n🔹 @{profile.get('username', '')}\n📝 {profile.get('bio', 'Био не указана')[:100]}"
        screenshot = await human_screenshot(page, 100, 100)
        await update.message.reply_photo(photo=screenshot, caption=text)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ /XTRENDS ============
async def xtrends(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("⚠️ Сначала открой браузер: /browser")
        return
    try:
        session = user_sessions[user_id]
        page = session["page"]
        await goto_url(page, "https://x.com/explore/tabs/trending")
        await page.wait_for_timeout(3000)
        
        trends = await page.evaluate("""
            () => {
                const trends = [];
                const items = document.querySelectorAll('[data-testid="trend"]');
                items.forEach((item, i) => {
                    if (i >= 10) return;
                    const text = item.textContent || '';
                    if (text) trends.push(text.trim());
                });
                return trends;
            }
        """)
        
        if trends:
            text = "📈 **Тренды**\n\n"
            for i, trend in enumerate(trends, 1):
                text += f"{i}. {trend[:50]}\n"
            await update.message.reply_text(text)
        else:
            await update.message.reply_text("❌ Тренды не найдены")
        
        screenshot = await human_screenshot(page, 100, 100)
        await update.message.reply_photo(photo=screenshot, caption="📸 Тренды")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============ ЗАПУСК ============
def run_flask():
    port = int(os.getenv("PORT", 8080))
    app_flask.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    
    bot_app = Application.builder().token(BOT_TOKEN).build()
    
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("browser", browser_command))
    bot_app.add_handler(CommandHandler("close", close_command))
    bot_app.add_handler(CommandHandler("go", go_command))
    bot_app.add_handler(CommandHandler("status", status_command))
    bot_app.add_handler(CommandHandler("screenshot", screenshot_command))
    bot_app.add_handler(CommandHandler("xlogin", xlogin))
    bot_app.add_handler(CommandHandler("xhome", xhome))
    bot_app.add_handler(CommandHandler("xprofile", xprofile))
    bot_app.add_handler(CommandHandler("xtrends", xtrends))
    
    print("✅ Бот запущен")
    bot_app.run_polling()

if __name__ == "__main__":
    main()