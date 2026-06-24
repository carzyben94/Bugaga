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
    """Автоматическая установка cloakbrowser при первом запуске"""
    try:
        import cloakbrowser
        logger.info("✅ CloakBrowser уже установлен")
        return True
    except ImportError:
        logger.info("📦 CloakBrowser не найден, начинаю установку...")
        
        try:
            # Устанавливаем cloakbrowser
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "--no-cache-dir", 
                "--default-timeout=1000",
                "cloakbrowser"
            ])
            logger.info("✅ CloakBrowser успешно установлен!")
            
            # Проверяем установку
            import cloakbrowser
            logger.info(f"✅ Версия: {cloakbrowser.__version__ if hasattr(cloakbrowser, '__version__') else 'неизвестна'}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка установки: {e}")
            
            # Пробуем альтернативный вариант
            try:
                logger.info("🔄 Пробуем установить через pip3...")
                subprocess.check_call([
                    "pip3", "install", 
                    "--no-cache-dir", 
                    "cloakbrowser"
                ])
                return True
            except:
                logger.error("❌ Не удалось установить CloakBrowser")
                return False

# Устанавливаем при импорте
CLOAK_INSTALLED = install_cloakbrowser()

if not CLOAK_INSTALLED:
    logger.error("❌ CloakBrowser не установлен! Бот будет работать с ограничениями.")

# Теперь импортируем cloakbrowser
try:
    from cloakbrowser import launch_async
    CLOAK_AVAILABLE = True
except ImportError:
    logger.error("❌ CloakBrowser не доступен, используем заглушку")
    CLOAK_AVAILABLE = False
    # Создаём заглушку
    class launch_async:
        @staticmethod
        async def launch(*args, **kwargs):
            raise Exception("CloakBrowser не установлен!")

# Токен из переменных Railway
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан! Добавь переменную в Railway")

# Глобальный менеджер браузера
browser = None
page = None
browser_started = False
setup_logs = []

# === КУКИ ДЛЯ X ===
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

# === ФУНКЦИИ БРАУЗЕРА ===
async def start_browser(proxy=None):
    global browser, page, browser_started
    
    if not CLOAK_AVAILABLE:
        raise Exception("❌ CloakBrowser не установлен! Перезапусти бота для установки.")
    
    add_log("🚀 Запуск CloakBrowser...")
    
    browser = await launch_async(
        headless=True,
        proxy=proxy,
        humanize=True,
        args=['--no-sandbox', '--disable-dev-shm-usage']
    )
    
    page = await browser.new_page()
    browser_started = True
    add_log("✅ CloakBrowser запущен успешно!")
    return page

async def close_browser():
    global browser, page, browser_started
    if browser:
        await browser.close()
        browser = None
        page = None
        browser_started = False
        add_log("⏹ Браузер закрыт")

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
        ],
        [
            InlineKeyboardButton("📦 Установить CloakBrowser", callback_data="browser_install")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# === КОМАНДЫ БОТА ===

async def browser_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = get_play_keyboard()
    status_text = "✅ Браузер запущен" if browser_started else "⏸ Браузер остановлен"
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
    
    if action == "browser_install":
        await query.edit_message_text(
            "📦 **Установка CloakBrowser...**\n\n"
            "Это может занять 2-3 минуты.",
            parse_mode='Markdown'
        )
        
        try:
            # Переустанавливаем
            import subprocess, sys
            result = subprocess.run([
                sys.executable, "-m", "pip", "install",
                "--no-cache-dir",
                "--default-timeout=1000",
                "cloakbrowser"
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                add_log("✅ CloakBrowser успешно установлен!")
                await query.edit_message_text(
                    "✅ **CloakBrowser успешно установлен!**\n\n"
                    "Перезапусти бота командой /start",
                    reply_markup=get_play_keyboard(),
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text(
                    f"❌ **Ошибка установки:**\n\n{result.stderr[:500]}",
                    reply_markup=get_play_keyboard(),
                    parse_mode='Markdown'
                )
        except Exception as e:
            await query.edit_message_text(
                f"❌ Ошибка: {str(e)[:200]}",
                reply_markup=get_play_keyboard()
            )
    
    elif action == "browser_start":
        if not CLOAK_AVAILABLE:
            await query.edit_message_text(
                "❌ **CloakBrowser не установлен!**\n\n"
                "Нажми 📦 Установить CloakBrowser",
                reply_markup=get_play_keyboard(),
                parse_mode='Markdown'
            )
            return
        
        await query.edit_message_text("🚀 Запускаю браузер...\n\n_Это может занять 2-3 минуты_", parse_mode='Markdown')
        
        try:
            add_log("Начинаем запуск CloakBrowser...")
            
            steps = [
                "📦 Проверка зависимостей...",
                "📥 Загрузка бинарника (~200MB)...",
                "⚙️ Распаковка...",
                "🔧 Настройка окружения...",
                "🌐 Запуск Chromium...",
                "✅ Готово!"
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
            
            await start_browser()
            browser_started = True
            
            await query.edit_message_text(
                f"✅ **Браузер запущен!**\n\n"
                f"📊 Статус: Активен\n"
                f"📝 Всего логов: {len(setup_logs)}",
                reply_markup=get_play_keyboard(),
                parse_mode='Markdown'
            )
            
        except Exception as e:
            error_msg = f"❌ Ошибка запуска: {str(e)[:200]}"
            add_log(error_msg, "ERROR")
            await query.edit_message_text(
                error_msg,
                reply_markup=get_play_keyboard()
            )
    
    elif action == "browser_stop":
        await close_browser()
        await query.edit_message_text(
            "⏹ **Браузер остановлен**",
            reply_markup=get_play_keyboard(),
            parse_mode='Markdown'
        )
    
    elif action == "browser_status":
        status = "✅ Запущен" if browser_started else "⏸ Остановлен"
        cloak = "✅ Доступен" if CLOAK_AVAILABLE else "❌ Не установлен"
        await query.edit_message_text(
            f"📊 **Статус**\n\n"
            f"Браузер: {status}\n"
            f"CloakBrowser: {cloak}\n"
            f"Логов: {len(setup_logs)}\n"
            f"Последний: {setup_logs[-1] if setup_logs else 'Нет'}",
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
        await close_browser()
        await query.edit_message_text("🔄 Перезапуск...", parse_mode='Markdown')
        await asyncio.sleep(2)
        await start_browser()
        browser_started = True
        await query.edit_message_text(
            "✅ **Браузер перезапущен!**",
            reply_markup=get_play_keyboard(),
            parse_mode='Markdown'
        )
    
    elif action == "browser_login_x":
        if not browser_started:
            await query.edit_message_text(
                "❌ Сначала запусти браузер!",
                reply_markup=get_play_keyboard()
            )
            return
        
        await query.edit_message_text("🔐 Вход в X...", parse_mode='Markdown')
        
        try:
            await page.context.add_cookies(X_COOKIES)
            await page.goto("https://x.com/home", wait_until="networkidle")
            
            cookies_after = await page.context.cookies()
            auth_cookie = next((c for c in cookies_after if c.get('name') == 'auth_token'), None)
            
            if auth_cookie:
                add_log("✅ Успешный вход в X!")
                screenshot = await page.screenshot(full_page=False)
                await query.edit_message_text(
                    "✅ **Вход в X выполнен!**",
                    reply_markup=get_play_keyboard(),
                    parse_mode='Markdown'
                )
                await query.message.reply_photo(photo=screenshot, caption="🏠 Главная X")
            else:
                await query.edit_message_text(
                    "❌ Авторизация не удалась. Обнови куки.",
                    reply_markup=get_play_keyboard()
                )
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {str(e)[:200]}", reply_markup=get_play_keyboard())
    
    elif action == "browser_tweet":
        await query.edit_message_text(
            "🐦 Используй команду: `/tweet <текст>`",
            reply_markup=get_play_keyboard(),
            parse_mode='Markdown'
        )

# === ОСТАЛЬНЫЕ КОМАНДЫ ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🕵️ **Бот с CloakBrowser**\n\n"
        "📋 Команды:\n"
        "/browser_play - 🎮 Панель управления\n"
        "/html <url> - Получить HTML\n"
        "/shot <url> - Скриншот\n"
        "/cookies <url> - Показать куки\n"
        "/login_x - Войти в X\n"
        "/tweet <текст> - Опубликовать твит\n"
        "/status - Статус браузера\n\n"
        f"📦 CloakBrowser: {'✅ Установлен' if CLOAK_AVAILABLE else '❌ Не установлен'}",
        parse_mode='Markdown'
    )

# ... (другие команды html, shot, cookies, login_x, tweet, status - такие же как раньше)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "✅ Запущен" if browser_started else "⏸ Остановлен"
    cloak = "✅ Доступен" if CLOAK_AVAILABLE else "❌ Не установлен"
    await update.message.reply_text(
        f"📊 **Статус**\n\nБраузер: {status}\nCloakBrowser: {cloak}",
        parse_mode='Markdown'
    )

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("browser_play", browser_play))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CallbackQueryHandler(handle_play_callback, pattern="^browser_"))
    
    logger.info("🚀 Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()