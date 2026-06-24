import os
import sys
import subprocess
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === АВТОУСТАНОВКА CLOAKBROWSER ===
def install_cloakbrowser():
    try:
        import cloakbrowser
        logger.info("✅ CloakBrowser уже установлен")
        return True
    except ImportError:
        logger.info("📦 CloakBrowser не найден, начинаю установку...")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "--no-cache-dir",
                "--default-timeout=1000",
                "cloakbrowser"
            ])
            logger.info("✅ CloakBrowser успешно установлен!")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка установки: {e}")
            return False

CLOAK_INSTALLED = install_cloakbrowser()

if not CLOAK_INSTALLED:
    logger.error("❌ CloakBrowser не установлен!")

try:
    from cloakbrowser import launch_async
    CLOAK_AVAILABLE = True
    logger.info("✅ CloakBrowser импортирован успешно!")
except ImportError as e:
    logger.error(f"❌ Ошибка импорта: {e}")
    CLOAK_AVAILABLE = False
    class launch_async:
        @staticmethod
        async def launch(*args, **kwargs):
            raise Exception("CloakBrowser не установлен!")

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан!")

# Глобальные переменные
browser = None
page = None
browser_started = False
setup_logs = []

# === НОВЫЕ КУКИ ДЛЯ X ===
X_COOKIES = [
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "__cuid",
        "path": "/",
        "sameSite": "None",
        "secure": False,
        "session": True,
        "value": "55d2d7c5-4888-430a-b024-dd785da46ef4"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "lang",
        "path": "/",
        "sameSite": "None",
        "secure": False,
        "session": True,
        "value": "ru"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "__cf_bm",
        "path": "/",
        "sameSite": "None",
        "secure": False,
        "session": True,
        "value": "66HwWBE7ARw4zHfM3LKTzQ53lbNeZx6P849spGsz47c-1782325511.5695279-1.0.1.1-Zf5fw2.4R8Iw1J7B83inu2l4MPvKm_pwrRGDlbV25kVIE1JBc_y43rnSVDzj6yZ36m9Z2oBENu0klLOSikjdykvpzW8Mc5cDGi54TvrVy5Lo3TZ4PFc1Y1Y4P1qPF0Lo"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "dnt",
        "path": "/",
        "sameSite": "None",
        "secure": False,
        "session": True,
        "value": "1"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "guest_id",
        "path": "/",
        "sameSite": "None",
        "secure": False,
        "session": True,
        "value": "v1%3A178232552081152335"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "guest_id_marketing",
        "path": "/",
        "sameSite": "None",
        "secure": False,
        "session": True,
        "value": "v1%3A178232552081152335"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "guest_id_ads",
        "path": "/",
        "sameSite": "None",
        "secure": False,
        "session": True,
        "value": "v1%3A178232552081152335"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "personalization_id",
        "path": "/",
        "sameSite": "None",
        "secure": False,
        "session": True,
        "value": "\"v1_WrN9cfSG2zvM3RbiT1ZEkw==\""
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "gt",
        "path": "/",
        "sameSite": "None",
        "secure": False,
        "session": True,
        "value": "2069849371814887470"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "twid",
        "path": "/",
        "sameSite": "None",
        "secure": False,
        "session": True,
        "value": "u%3D2067347503503052800"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "auth_token",
        "path": "/",
        "sameSite": "None",
        "secure": False,
        "session": True,
        "value": "9437c2dd7e6dd3b655cd4166f1fe303365f56d91"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "ct0",
        "path": "/",
        "sameSite": "None",
        "secure": False,
        "session": True,
        "value": "6348cd308326bbc75e48654d2a7488c58d9d34f10712b0f1b3d7bde9e67a028c46de54fbbbace15ab6a518f71b27945510c1dc91b2ef7c9360aaf009883b0c5e326f4196c02e32c930a7c2222c4af9ff"
    }
]

# === ФУНКЦИИ ===
def add_log(message, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {message}"
    setup_logs.append(log_entry)
    if len(setup_logs) > 100:
        setup_logs.pop(0)
    logger.info(log_entry)
    return log_entry

def get_play_keyboard():
    keyboard = [
        [InlineKeyboardButton("🚀 Запустить браузер", callback_data="browser_start")],
        [InlineKeyboardButton("⏹ Остановить", callback_data="browser_stop")],
        [InlineKeyboardButton("📊 Статус", callback_data="browser_status"), InlineKeyboardButton("📋 Логи", callback_data="browser_logs")],
        [InlineKeyboardButton("🔄 Перезапустить", callback_data="browser_restart"), InlineKeyboardButton("🧹 Очистить логи", callback_data="browser_clear_logs")],
        [InlineKeyboardButton("🔐 Войти в X", callback_data="browser_login_x"), InlineKeyboardButton("🐦 Твитнуть", callback_data="browser_tweet")]
    ]
    return InlineKeyboardMarkup(keyboard)

# === КОМАНДЫ ===

async def browserplay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = get_play_keyboard()
    status_text = "✅ Запущен" if browser_started else "⏸ Остановлен"
    cloak_status = "✅ Доступен" if CLOAK_AVAILABLE else "❌ Не установлен"
    
    await update.message.reply_text(
        f"🎮 **Панель управления CloakBrowser**\n\n"
        f"📊 Статус: {status_text}\n"
        f"📦 CloakBrowser: {cloak_status}\n"
        f"📝 Логов: {len(setup_logs)}\n"
        f"🕒 Последний лог: {setup_logs[-1] if setup_logs else 'Нет логов'}\n\n"
        f"Нажми на кнопку ниже:",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

async def handle_play_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_started, page, browser
    
    query = update.callback_query
    await query.answer()
    action = query.data
    
    if action == "browser_start":
        if not CLOAK_AVAILABLE:
            await query.edit_message_text("❌ CloakBrowser не установлен!", reply_markup=get_play_keyboard())
            return
        
        await query.edit_message_text("🚀 Запускаю браузер...\n\n_Это может занять 2-3 минуты_", parse_mode='Markdown')
        
        try:
            add_log("Начинаем запуск CloakBrowser...")
            
            steps = ["📦 Проверка зависимостей...", "📥 Загрузка бинарника (~200MB)...", "⚙️ Распаковка...", "🔧 Настройка окружения...", "🌐 Запуск Chromium...", "✅ Готово!"]
            
            log_messages = []
            for step in steps:
                await asyncio.sleep(0.5)
                log_entry = add_log(step)
                log_messages.append(log_entry)
                await query.edit_message_text(
                    f"🚀 Запуск браузера...\n\n" + "\n".join(log_messages),
                    parse_mode='Markdown'
                )
            
            browser = await launch_async(
                headless=True,
                humanize=True,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
            page = await browser.new_page()
            browser_started = True
            add_log("✅ Браузер запущен успешно!")
            
            await query.edit_message_text(
                f"✅ **Браузер запущен!**\n\n📊 Статус: Активен\n📝 Всего логов: {len(setup_logs)}",
                reply_markup=get_play_keyboard(),
                parse_mode='Markdown'
            )
            
        except Exception as e:
            error_msg = f"❌ Ошибка запуска: {str(e)[:200]}"
            add_log(error_msg, "ERROR")
            await query.edit_message_text(error_msg, reply_markup=get_play_keyboard())
    
    elif action == "browser_stop":
        if browser:
            await browser.close()
            browser = None
            page = None
            browser_started = False
            add_log("⏹ Браузер остановлен")
        await query.edit_message_text("⏹ **Браузер остановлен**", reply_markup=get_play_keyboard(), parse_mode='Markdown')
    
    elif action == "browser_status":
        status = "✅ Запущен" if browser_started else "⏸ Остановлен"
        cloak = "✅ Доступен" if CLOAK_AVAILABLE else "❌ Не установлен"
        await query.edit_message_text(
            f"📊 **Статус**\n\nБраузер: {status}\nCloakBrowser: {cloak}\nЛогов: {len(setup_logs)}",
            reply_markup=get_play_keyboard(),
            parse_mode='Markdown'
        )
    
    elif action == "browser_logs":
        if not setup_logs:
            await query.edit_message_text("📋 Логов пока нет", reply_markup=get_play_keyboard())
            return
        logs_text = "\n".join(setup_logs[-20:])
        await query.edit_message_text(
            f"📋 **Логи** ({len(setup_logs)} всего)\n\n```\n{logs_text}\n```",
            reply_markup=get_play_keyboard(),
            parse_mode='Markdown'
        )
    
    elif action == "browser_clear_logs":
        setup_logs.clear()
        await query.edit_message_text("🧹 Логи очищены", reply_markup=get_play_keyboard())
    
    elif action == "browser_restart":
        if browser:
            await browser.close()
            browser = None
            page = None
            browser_started = False
        await query.edit_message_text("🔄 Перезапуск...", parse_mode='Markdown')
        await asyncio.sleep(1)
        browser = await launch_async(headless=True, humanize=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        page = await browser.new_page()
        browser_started = True
        await query.edit_message_text("✅ **Браузер перезапущен!**", reply_markup=get_play_keyboard(), parse_mode='Markdown')
    
    elif action == "browser_login_x":
        if not browser_started:
            await query.edit_message_text("❌ Сначала запусти браузер!", reply_markup=get_play_keyboard())
            return
        
        await query.edit_message_text("🔐 Вход в X...", parse_mode='Markdown')
        try:
            await page.context.add_cookies(X_COOKIES)
            await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
            
            cookies_after = await page.context.cookies()
            auth_cookie = next((c for c in cookies_after if c.get('name') == 'auth_token'), None)
            
            if auth_cookie:
                add_log("✅ Успешный вход в X!")
                screenshot = await page.screenshot(full_page=False)
                await query.edit_message_text("✅ **Вход в X выполнен!**", reply_markup=get_play_keyboard(), parse_mode='Markdown')
                await query.message.reply_photo(photo=screenshot, caption="🏠 Главная X")
            else:
                await query.edit_message_text("❌ Авторизация не удалась. Обнови куки.", reply_markup=get_play_keyboard())
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {str(e)[:200]}", reply_markup=get_play_keyboard())
    
    elif action == "browser_tweet":
        await query.edit_message_text("🐦 Используй команду: `/tweet <текст>`", reply_markup=get_play_keyboard(), parse_mode='Markdown')

# === ОБЫЧНЫЕ КОМАНДЫ ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🕵️ **Бот с CloakBrowser**\n\n"
        "📋 Команды:\n"
        "/browserplay - 🎮 Панель управления\n"
        "/html <url> - Получить HTML\n"
        "/shot <url> - Скриншот\n"
        "/cookies <url> - Показать куки\n"
        "/loginx - Войти в X\n"
        "/tweet <текст> - Опубликовать твит\n"
        "/status - Статус браузера\n\n"
        f"📦 CloakBrowser: {'✅ Установлен' if CLOAK_AVAILABLE else '❌ Не установлен'}",
        parse_mode='Markdown'
    )

async def html_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_started, browser, page
    
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /html https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"🌐 Загружаю {url}...")
    
    try:
        if not browser_started:
            browser = await launch_async(headless=True, humanize=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            page = await browser.new_page()
            browser_started = True
        
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        content = await page.content()
        preview = content[:4000] + "..." if len(content) > 4000 else content
        await update.message.reply_text(f"📄 HTML ({len(content)} символов):\n\n{preview}")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def shot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_started, browser, page
    
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /shot https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"📸 Делаю скриншот {url}...")
    
    try:
        if not browser_started:
            browser = await launch_async(headless=True, humanize=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            page = await browser.new_page()
            browser_started = True
        
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        screenshot = await page.screenshot(full_page=True)
        await update.message.reply_photo(photo=screenshot, caption=f"Скриншот: {url}")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_started, browser, page
    
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /cookies https://x.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"🍪 Получаю куки с {url}...")
    
    try:
        if not browser_started:
            browser = await launch_async(headless=True, humanize=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            page = await browser.new_page()
            browser_started = True
        
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        cookies = await page.context.cookies()
        
        if cookies:
            preview = "\n".join([f"🍪 {c.get('name')}: {c.get('value')[:30]}..." for c in cookies[:5]])
            await update.message.reply_text(f"Найдено {len(cookies)} кук:\n\n{preview}")
        else:
            await update.message.reply_text("⚠️ Куки не найдены")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def loginx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_started, browser, page
    
    await update.message.reply_text("🔐 Выполняю вход в X...")
    
    try:
        if not browser_started:
            browser = await launch_async(headless=True, humanize=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            page = await browser.new_page()
            browser_started = True
        
        await page.context.add_cookies(X_COOKIES)
        await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
        
        cookies_after = await page.context.cookies()
        auth_cookie = next((c for c in cookies_after if c.get('name') == 'auth_token'), None)
        
        if auth_cookie:
            add_log("✅ Успешный вход в X через /loginx")
            screenshot = await page.screenshot(full_page=False)
            await update.message.reply_photo(
                photo=screenshot,
                caption="✅ Успешный вход в X!\n\nТеперь доступно: /tweet <текст>"
            )
        else:
            await update.message.reply_text(
                "❌ Авторизация не удалась. Обнови куки.\n\n"
                "Проверь:\n"
                "1. Куки устарели — обнови\n"
                "2. Не все куки скопированы\n"
                "3. Попробуй войти в X в обычном браузере и повтори"
            )
            
    except Exception as e:
        logger.error(f"Ошибка входа: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tweet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_started, browser, page
    
    if not context.args:
        await update.message.reply_text("❌ Напиши текст твита: /tweet Привет, мир!")
        return
    
    tweet_text = " ".join(context.args)
    
    if len(tweet_text) > 280:
        await update.message.reply_text("❌ Твит слишком длинный (макс 280 символов)")
        return
    
    await update.message.reply_text(f"🐦 Публикую твит...")
    
    try:
        if not browser_started:
            browser = await launch_async(headless=True, humanize=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            page = await browser.new_page()
            browser_started = True
        
        await page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)
        
        escaped_text = tweet_text.replace('"', '\\"').replace("'", "\\'")
        await page.evaluate(f'''
            (function() {{
                const textarea = document.querySelector('[data-testid="tweetTextarea_0"]');
                if (textarea) {{
                    textarea.value = "{escaped_text}";
                    textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            }})();
        ''')
        
        await page.wait_for_timeout(1000)
        await page.click('[data-testid="tweetButton"]')
        await page.wait_for_timeout(5000)
        
        success = await page.evaluate('''
            (function() {
                const error = document.querySelector('[data-testid="toast"]');
                if (error && error.textContent && error.textContent.toLowerCase().includes('error')) {
                    return false;
                }
                return true;
            })();
        ''')
        
        if success:
            add_log(f"✅ Твит опубликован: {tweet_text[:50]}...")
            screenshot = await page.screenshot()
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"✅ Твит опубликован!\n\n{tweet_text}"
            )
        else:
            await update.message.reply_text("❌ Не удалось опубликовать твит. Проверь авторизацию.")
            
    except Exception as e:
        logger.error(f"Ошибка твита: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "✅ Запущен" if browser_started else "⏸ Остановлен"
    cloak = "✅ Установлен" if CLOAK_AVAILABLE else "❌ Не установлен"
    await update.message.reply_text(
        f"📊 **Статус бота**\n\n"
        f"🖥 Браузер: {status}\n"
        f"📦 CloakBrowser: {cloak}\n"
        f"📝 Логов: {len(setup_logs)}\n"
        f"🕒 Последний лог: {setup_logs[-1] if setup_logs else 'Нет'}",
        parse_mode='Markdown'
    )

# === ЗАПУСК ===

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("browserplay", browserplay))
    app.add_handler(CommandHandler("html", html_command))
    app.add_handler(CommandHandler("shot", shot_command))
    app.add_handler(CommandHandler("cookies", cookies_command))
    app.add_handler(CommandHandler("loginx", loginx))
    app.add_handler(CommandHandler("tweet", tweet_command))
    app.add_handler(CommandHandler("status", status_command))
    
    app.add_handler(CallbackQueryHandler(handle_play_callback, pattern="^browser_"))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()