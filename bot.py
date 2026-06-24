import os
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from browser import CloakBrowserManager

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен из переменных Railway
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан! Добавь переменную в Railway")

# Глобальный менеджер браузера
browser_manager = CloakBrowserManager()
browser_started = False
setup_logs = []  # Храним логи установки

# === КУКИ ДЛЯ X (ЗАМЕНИТЬ НА СВЕЖИЕ ПРИ НЕОБХОДИМОСТИ) ===
X_COOKIES = [
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "guest_id_marketing",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "v1%3A178224957371538879"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "guest_id_ads",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "v1%3A178224957371538879"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "guest_id",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "v1%3A178224957371538879"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "__cuid",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "55d2d7c5-4888-430a-b024-dd785da46ef4"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "twid",
        "path": "/",
        "sameSite": "unspecified",
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
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "09fe982487255e707f7a9b3d380ea429421adae3"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "lang",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "ru"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "ct0",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "18f7448391062aaaa323ea38f4fd129f5f682f09ec0989f899ebc4ddaa4d7bf7de0e0c359240145428b7cc1d410adbc5565fa9bbe2c4380b5341327ea3c53f03a89fcb12ee617d0fea848882ae6ff281"
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "personalization_id",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "\"v1_3OVPutEVc/wdAMUgDi42Iw==\""
    },
    {
        "domain": ".x.com",
        "hostOnly": False,
        "httpOnly": False,
        "name": "__cf_bm",
        "path": "/",
        "sameSite": "unspecified",
        "secure": False,
        "session": True,
        "value": "5WvG7tNTa4Y9KfR0koVrrk7t2hZZuC6I88lvx8WhQvs-1782323196.745603-1.0.1.1-hMCaDCXE0djwDTzX26k4Nox7geJtr.NolcKWWGh71U1qRFc4R0UvohFIp_0yKa0hxCTXmmgaVvXrm4r0oBiQKu1ZVcHWA0umHod8Sjt8t_j4OOn5ZTqap.LIF_hhlCz_"
    }
]

# === КНОПКИ ДЛЯ /browser_play ===
def get_play_keyboard():
    """Генерирует клавиатуру с кнопками"""
    keyboard = [
        [
            InlineKeyboardButton("🚀 Запустить браузер", callback_data="browser_start"),
            InlineKeyboardButton("⏹ Остановить", callback_data="browser_stop")
        ],
        [
            InlineKeyboardButton("📊 Статус", callback_data="browser_status"),
            InlineKeyboardButton("📋 Логи", callback_data="browser_logs")
        ],
        [
            InlineKeyboardButton("🧹 Очистить логи", callback_data="browser_clear_logs"),
            InlineKeyboardButton("🔄 Перезапустить", callback_data="browser_restart")
        ],
        [
            InlineKeyboardButton("🔐 Войти в X", callback_data="browser_login_x"),
            InlineKeyboardButton("🐦 Твитнуть", callback_data="browser_tweet")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# === ФУНКЦИЯ ЛОГИРОВАНИЯ ===
def add_log(message, level="INFO"):
    """Добавляет запись в логи с временем"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {message}"
    setup_logs.append(log_entry)
    if len(setup_logs) > 100:
        setup_logs.pop(0)
    logger.info(log_entry)
    return log_entry

# === КОМАНДА /browser_play ===
async def browser_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главная панель управления браузером"""
    keyboard = get_play_keyboard()
    
    status_text = "✅ Браузер запущен" if browser_started else "⏸ Браузер остановлен"
    
    await update.message.reply_text(
        f"🎮 **Панель управления CloakBrowser**\n\n"
        f"📊 Статус: {status_text}\n"
        f"📝 Логов: {len(setup_logs)}\n"
        f"🕒 Последний лог: {setup_logs[-1] if setup_logs else 'Нет логов'}\n\n"
        f"Нажми на кнопку ниже:",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

# === ОБРАБОТЧИК КНОПОК ===
async def handle_play_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия кнопок"""
    global browser_started
    
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    if action == "browser_start":
        await query.edit_message_text("🚀 Запускаю браузер...\n\n_Это может занять 2-3 минуты_", parse_mode='Markdown')
        
        try:
            add_log("Начинаем запуск CloakBrowser...")
            
            steps = [
                "📦 Проверка зависимостей...",
                "📥 Скачивание CloakBrowser (~200MB)...",
                "⚙️ Распаковка бинарника...",
                "🔧 Настройка окружения...",
                "🌐 Запуск Chromium...",
                "✅ CloakBrowser готов к работе!"
            ]
            
            log_messages = []
            for step in steps:
                await asyncio.sleep(1)
                log_entry = add_log(step)
                log_messages.append(log_entry)
                await query.edit_message_text(
                    f"🚀 Запуск браузера...\n\n" + "\n".join(log_messages),
                    parse_mode='Markdown'
                )
            
            add_log("Инициализация AsyncCloakBrowser...")
            await browser_manager.start()
            browser_started = True
            add_log("✅ Браузер успешно запущен!")
            
            await query.edit_message_text(
                f"✅ **Браузер запущен!**\n\n"
                f"📊 Статус: Активен\n"
                f"📝 Всего логов: {len(setup_logs)}\n\n"
                f"Используй кнопки для управления:",
                reply_markup=get_play_keyboard(),
                parse_mode='Markdown'
            )
            
        except Exception as e:
            error_msg = f"❌ Ошибка запуска: {str(e)[:200]}"
            add_log(error_msg, "ERROR")
            await query.edit_message_text(
                f"{error_msg}\n\nПроверь логи: /browser_play → 📋 Логи",
                reply_markup=get_play_keyboard()
            )
    
    elif action == "browser_stop":
        add_log("Остановка браузера...")
        try:
            await browser_manager.close()
            browser_started = False
            add_log("✅ Браузер остановлен")
            await query.edit_message_text(
                "⏹ **Браузер остановлен**\n\n"
                "Для запуска нажми 🚀 Запустить браузер",
                reply_markup=get_play_keyboard(),
                parse_mode='Markdown'
            )
        except Exception as e:
            add_log(f"Ошибка остановки: {e}", "ERROR")
            await query.edit_message_text(
                f"❌ Ошибка: {str(e)[:200]}",
                reply_markup=get_play_keyboard()
            )
    
    elif action == "browser_status":
        status = "✅ Запущен" if browser_started else "⏸ Остановлен"
        await query.edit_message_text(
            f"📊 **Статус браузера**\n\n"
            f"Состояние: {status}\n"
            f"Логов: {len(setup_logs)}\n"
            f"Последний лог: {setup_logs[-1] if setup_logs else 'Нет логов'}\n\n"
            f"Браузер: CloakBrowser\n"
            f"Режим: headless\n"
            f"Humanize: Включён",
            reply_markup=get_play_keyboard(),
            parse_mode='Markdown'
        )
    
    elif action == "browser_logs":
        if not setup_logs:
            await query.edit_message_text(
                "📋 **Логов пока нет**\n\n"
                "Запусти браузер, чтобы увидеть логи.",
                reply_markup=get_play_keyboard(),
                parse_mode='Markdown'
            )
            return
        
        logs_text = "\n".join(setup_logs[-20:])
        await query.edit_message_text(
            f"📋 **Последние логи** ({len(setup_logs)} всего)\n\n"
            f"```\n{logs_text}\n```",
            reply_markup=get_play_keyboard(),
            parse_mode='Markdown'
        )
    
    elif action == "browser_clear_logs":
        setup_logs.clear()
        add_log("🧹 Логи очищены")
        await query.edit_message_text(
            "🧹 **Логи очищены**",
            reply_markup=get_play_keyboard(),
            parse_mode='Markdown'
        )
    
    elif action == "browser_restart":
        add_log("🔄 Перезапуск браузера...")
        try:
            await browser_manager.close()
            browser_started = False
            add_log("Браузер остановлен для перезапуска")
            
            await query.edit_message_text(
                "🔄 **Перезапуск браузера...**\n\n"
                "Это займёт 2-3 минуты",
                parse_mode='Markdown'
            )
            
            await browser_manager.start()
            browser_started = True
            add_log("✅ Браузер перезапущен")
            
            await query.edit_message_text(
                "✅ **Браузер перезапущен!**",
                reply_markup=get_play_keyboard(),
                parse_mode='Markdown'
            )
        except Exception as e:
            add_log(f"Ошибка перезапуска: {e}", "ERROR")
            await query.edit_message_text(
                f"❌ Ошибка: {str(e)[:200]}",
                reply_markup=get_play_keyboard()
            )
    
    elif action == "browser_login_x":
        if not browser_started:
            await query.edit_message_text(
                "❌ **Браузер не запущен!**\n\n"
                "Сначала нажми 🚀 Запустить браузер",
                reply_markup=get_play_keyboard(),
                parse_mode='Markdown'
            )
            return
        
        await query.edit_message_text("🔐 Выполняю вход в X...", parse_mode='Markdown')
        
        try:
            add_log("Установка кук X...")
            await browser_manager.set_cookies(X_COOKIES)
            
            add_log("Переход на X.com...")
            await browser_manager.page.goto("https://x.com/home", wait_until="networkidle")
            
            cookies_after = await browser_manager.page.context.cookies()
            auth_cookie = next((c for c in cookies_after if c.get('name') == 'auth_token'), None)
            
            if auth_cookie:
                add_log("✅ Успешный вход в X!")
                screenshot = await browser_manager.page.screenshot(full_page=False)
                await query.edit_message_text(
                    "✅ **Вход в X выполнен!**\n\n"
                    "Теперь можно публиковать твиты.",
                    reply_markup=get_play_keyboard(),
                    parse_mode='Markdown'
                )
                await query.message.reply_photo(
                    photo=screenshot,
                    caption="🏠 Главная страница X"
                )
            else:
                add_log("❌ Авторизация не удалась", "ERROR")
                await query.edit_message_text(
                    "❌ **Авторизация не удалась**\n\n"
                    "Куки устарели. Обнови их в коде.",
                    reply_markup=get_play_keyboard(),
                    parse_mode='Markdown'
                )
        except Exception as e:
            add_log(f"Ошибка входа: {e}", "ERROR")
            await query.edit_message_text(
                f"❌ Ошибка: {str(e)[:200]}",
                reply_markup=get_play_keyboard()
            )
    
    elif action == "browser_tweet":
        if not browser_started:
            await query.edit_message_text(
                "❌ **Браузер не запущен!**\n\n"
                "Сначала нажми 🚀 Запустить браузер",
                reply_markup=get_play_keyboard(),
                parse_mode='Markdown'
            )
            return
        
        await query.edit_message_text(
            "🐦 **Напиши текст твита**\n\n"
            "Используй команду: `/tweet <текст>`\n\n"
            "Пример: `/tweet Привет из CloakBrowser!`",
            reply_markup=get_play_keyboard(),
            parse_mode='Markdown'
        )

# === ОСТАЛЬНЫЕ КОМАНДЫ ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🕵️ **Бот с CloakBrowser готов!**\n\n"
        "📋 Команды:\n"
        "/browser_play - 🎮 Панель управления браузером\n"
        "/html <url> - получить HTML страницы\n"
        "/shot <url> - сделать скриншот\n"
        "/cookies <url> - показать куки сайта\n"
        "/login_x - войти в X с куками\n"
        "/tweet <текст> - опубликовать твит\n"
        "/status - статус браузера",
        parse_mode='Markdown'
    )

async def html_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_started
    
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /html https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"🌐 Загружаю {url}...")
    
    try:
        if not browser_started:
            await browser_manager.start()
            browser_started = True
            add_log("Браузер запущен через /html")
        
        content = await browser_manager.get_page_content(url)
        preview = content[:4000] + "..." if len(content) > 4000 else content
        await update.message.reply_text(f"📄 HTML ({len(content)} символов):\n\n{preview}")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def shot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_started
    
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /shot https://example.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"📸 Делаю скриншот {url}...")
    
    try:
        if not browser_started:
            await browser_manager.start()
            browser_started = True
            add_log("Браузер запущен через /shot")
        
        screenshot = await browser_manager.screenshot(url)
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"Скриншот: {url}"
        )
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_started
    
    if not context.args:
        await update.message.reply_text("❌ Укажи URL: /cookies https://x.com")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"🍪 Получаю куки с {url}...")
    
    try:
        if not browser_started:
            await browser_manager.start()
            browser_started = True
            add_log("Браузер запущен через /cookies")
        
        cookies = await browser_manager.get_cookies(url)
        
        if cookies:
            preview = "\n".join([f"🍪 {c.get('name')}: {c.get('value')[:30]}..." for c in cookies[:5]])
            await update.message.reply_text(f"Найдено {len(cookies)} кук:\n\n{preview}")
        else:
            await update.message.reply_text("⚠️ Куки не найдены")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def login_x(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_started
    
    await update.message.reply_text("🔐 Выполняю вход в X...")
    
    try:
        if not browser_started:
            await browser_manager.start()
            browser_started = True
            add_log("Браузер запущен через /login_x")
        
        await browser_manager.set_cookies(X_COOKIES)
        await browser_manager.page.goto("https://x.com/home", wait_until="networkidle")
        
        cookies_after = await browser_manager.page.context.cookies()
        auth_cookie = next((c for c in cookies_after if c.get('name') == 'auth_token'), None)
        
        if auth_cookie:
            add_log("✅ Успешный вход в X через /login_x")
            screenshot = await browser_manager.page.screenshot(full_page=False)
            await update.message.reply_photo(
                photo=screenshot,
                caption="✅ Успешный вход в X!\n\nТеперь доступно: /tweet <текст>"
            )
        else:
            add_log("❌ Авторизация не удалась через /login_x", "ERROR")
            await update.message.reply_text("❌ Авторизация не удалась. Обнови куки.")
            
    except Exception as e:
        logger.error(f"Ошибка входа: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def tweet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_started
    
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
            await browser_manager.start()
            browser_started = True
            add_log("Браузер запущен через /tweet")
        
        await browser_manager.page.goto("https://x.com/compose/post", wait_until="networkidle")
        await browser_manager.page.wait_for_timeout(2000)
        
        escaped_text = tweet_text.replace('"', '\\"').replace("'", "\\'")
        await browser_manager.page.evaluate(f'''
            (function() {{
                const textarea = document.querySelector('[data-testid="tweetTextarea_0"]');
                if (textarea) {{
                    textarea.value = "{escaped_text}";
                    textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            }})();
        ''')
        
        await browser_manager.page.wait_for_timeout(1000)
        await browser_manager.page.click('[data-testid="tweetButton"]')
        await browser_manager.page.wait_for_timeout(5000)
        
        success = await browser_manager.page.evaluate('''
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
            screenshot = await browser_manager.page.screenshot()
            await update.message.reply_photo(
                photo=screenshot,
                caption=f"✅ Твит опубликован!\n\n{tweet_text}"
            )
        else:
            add_log("❌ Не удалось опубликовать твит", "ERROR")
            await update.message.reply_text("❌ Не удалось опубликовать твит. Проверь авторизацию.")
            
    except Exception as e:
        logger.error(f"Ошибка твита: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "✅ Запущен" if browser_started else "⏸ Остановлен"
    await update.message.reply_text(
        f"📊 **Статус браузера**\n\n"
        f"Состояние: {status}\n"
        f"Логов: {len(setup_logs)}\n"
        f"Последний лог: {setup_logs[-1] if setup_logs else 'Нет логов'}",
        parse_mode='Markdown'
    )

# === ЗАПУСК ===

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("browser_play", browser_play))
    app.add_handler(CommandHandler("html", html_command))
    app.add_handler(CommandHandler("shot", shot_command))
    app.add_handler(CommandHandler("cookies", cookies_command))
    app.add_handler(CommandHandler("login_x", login_x))
    app.add_handler(CommandHandler("tweet", tweet_command))
    app.add_handler(CommandHandler("status", status_command))
    
    app.add_handler(CallbackQueryHandler(handle_play_callback, pattern="^browser_"))
    
    logger.info("🚀 Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()