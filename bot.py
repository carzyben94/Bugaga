import os
import sys
import subprocess
import logging
import asyncio
import json
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === ГЛОБАЛЬНЫЕ НАСТРОЙКИ ===
SCREENSHOT_TIMEOUT = 60000  # 60 секунд на скриншот
PAGE_TIMEOUT = 60000        # 60 секунд на загрузку страницы

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

# === КУКИ ПО УМОЛЧАНИЮ (пустые, будут заменены пользователем) ===
X_COOKIES = []

# === ФУНКЦИЯ ДЛЯ ИСПРАВЛЕНИЯ URL ===
def fix_url(url):
    """Добавляет https:// если отсутствует"""
    if not url:
        return url
    if not url.startswith(('http://', 'https://')):
        return f'https://{url}'
    return url

# === ФУНКЦИИ ===
def add_log(message, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {message}"
    setup_logs.append(log_entry)
    if len(setup_logs) > 100:
        setup_logs.pop(0)
    logger.info(log_entry)
    return log_entry

def parse_cookies_from_text(text):
    """
    Парсит куки из текста и УДАЛЯЕТ sameSite
    Поддерживает форматы:
    - JSON: [{"name": "...", "value": "...", ...}]
    - Cookie string: "name1=value1; name2=value2"
    - Пары с новой строки
    """
    text = text.strip()
    
    # Пробуем как JSON
    try:
        cookies = json.loads(text)
        if isinstance(cookies, list):
            result = []
            for c in cookies:
                # Берём только нужные поля
                cookie = {
                    "name": c.get("name"),
                    "value": c.get("value"),
                    "domain": c.get("domain", ".x.com"),
                    "path": c.get("path", "/")
                }
                # Если path = "\/" - исправляем
                if cookie["path"] == "\\/":
                    cookie["path"] = "/"
                # Проверяем что есть name и value
                if cookie["name"] and cookie["value"]:
                    result.append(cookie)
            if result:
                return result
    except:
        pass
    
    # Пробуем как cookie string
    cookies = []
    pairs = re.findall(r'([a-zA-Z_][a-zA-Z0-9_\-]*)\s*=\s*([^;]+)', text)
    for name, value in pairs:
        cookies.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": ".x.com",
            "path": "/"
        })
    
    if len(cookies) >= 2:
        return cookies
    
    # Пробуем найти JSON в тексте
    json_match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
    if json_match:
        try:
            cookies = json.loads(json_match.group())
            if isinstance(cookies, list) and len(cookies) > 0:
                result = []
                for c in cookies:
                    cookie = {
                        "name": c.get("name"),
                        "value": c.get("value"),
                        "domain": c.get("domain", ".x.com"),
                        "path": c.get("path", "/")
                    }
                    if cookie["path"] == "\\/":
                        cookie["path"] = "/"
                    if cookie["name"] and cookie["value"]:
                        result.append(cookie)
                return result
        except:
            pass
    
    return None

def get_play_keyboard():
    keyboard = [
        [InlineKeyboardButton("🚀 Запустить браузер", callback_data="browser_start")],
        [InlineKeyboardButton("⏹ Остановить", callback_data="browser_stop")],
        [InlineKeyboardButton("📊 Статус", callback_data="browser_status"), InlineKeyboardButton("📋 Логи", callback_data="browser_logs")],
        [InlineKeyboardButton("🔄 Перезапустить", callback_data="browser_restart"), InlineKeyboardButton("🧹 Очистить логи", callback_data="browser_clear_logs")],
        [InlineKeyboardButton("🔐 Войти в X", callback_data="browser_login_x"), InlineKeyboardButton("🐦 Твитнуть", callback_data="browser_tweet")],
        [InlineKeyboardButton("🎬 Watch X", callback_data="browser_watch_x")],
        [InlineKeyboardButton("🍪 Вставить куки", callback_data="browser_input_cookies")]
    ]
    return InlineKeyboardMarkup(keyboard)

# === КОМАНДЫ ===

async def browserplay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = get_play_keyboard()
    status_text = "✅ Запущен" if browser_started else "⏸ Остановлен"
    cloak_status = "✅ Доступен" if CLOAK_AVAILABLE else "❌ Не установлен"
    cookies_count = len(X_COOKIES)
    
    await update.message.reply_text(
        f"🎮 **Панель управления CloakBrowser**\n\n"
        f"📊 Статус: {status_text}\n"
        f"📦 CloakBrowser: {cloak_status}\n"
        f"🍪 Кук загружено: {cookies_count}\n"
        f"📝 Логов: {len(setup_logs)}\n"
        f"🕒 Последний лог: {setup_logs[-1] if setup_logs else 'Нет логов'}\n\n"
        f"Нажми на кнопку ниже:",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

async def handle_play_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_started, page, browser, X_COOKIES
    
    query = update.callback_query
    await query.answer()
    action = query.data
    
    if action == "browser_input_cookies":
        await query.edit_message_text(
            "🍪 **Вставь куки в чат**\n\n"
            "Отправь куки в одном из форматов:\n\n"
            "1️⃣ **JSON** (из расширения Cookie-Editor):\n"
            "```json\n[{\"name\":\"auth_token\",\"value\":\"...\"}, ...]\n```\n\n"
            "2️⃣ **Строка кук** (из браузера):\n"
            "```\nauth_token=12345; ct0=67890; twid=u%3D123\n```\n\n"
            "3️⃣ **Просто пары** (каждая с новой строки):\n"
            "```\nauth_token=12345\nct0=67890\ntwid=u%3D123\n```\n\n"
            "⚠️ **Важно:** куки должны быть с сайта `.x.com`\n\n"
            "Просто отправь текст с куками в этот чат!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Назад", callback_data="browser_back")]
            ]),
            parse_mode='Markdown'
        )
        # Сохраняем состояние, что ждём куки
        context.user_data['waiting_for_cookies'] = True
        return
    
    if action == "browser_back":
        await query.edit_message_text(
            "🎮 **Панель управления CloakBrowser**\n\n"
            "Нажми на кнопку ниже:",
            reply_markup=get_play_keyboard(),
            parse_mode='Markdown'
        )
        return
    
    if action == "browser_watch_x":
        await watch_x_callback(update, context)
        return
    
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
            f"📊 **Статус**\n\nБраузер: {status}\nCloakBrowser: {cloak}\nКук загружено: {len(X_COOKIES)}\nЛогов: {len(setup_logs)}",
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
        
        if not X_COOKIES:
            await query.edit_message_text(
                "❌ **Нет кук!**\n\n"
                "Сначала вставь куки через кнопку 🍪 Вставить куки",
                reply_markup=get_play_keyboard()
            )
            return
        
        await query.edit_message_text("🔐 Вход в X...", parse_mode='Markdown')
        try:
            await page.context.add_cookies(X_COOKIES)
            await page.goto(fix_url("x.com/home"), wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
            
            cookies_after = await page.context.cookies()
            auth_cookie = next((c for c in cookies_after if c.get('name') == 'auth_token'), None)
            
            if auth_cookie:
                add_log("✅ Успешный вход в X!")
                screenshot = await page.screenshot(full_page=False, timeout=SCREENSHOT_TIMEOUT)
                await query.edit_message_text("✅ **Вход в X выполнен!**", reply_markup=get_play_keyboard(), parse_mode='Markdown')
                await query.message.reply_photo(photo=screenshot, caption="🏠 Главная X")
            else:
                await query.edit_message_text("❌ Авторизация не удалась. Обнови куки.", reply_markup=get_play_keyboard())
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {str(e)[:200]}", reply_markup=get_play_keyboard())
    
    elif action == "browser_tweet":
        await query.edit_message_text("🐦 Используй команду: `/tweet <текст>`", reply_markup=get_play_keyboard(), parse_mode='Markdown')

# === ОБРАБОТЧИК СООБЩЕНИЙ ДЛЯ КУК ===

async def handle_cookies_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения с куками"""
    global X_COOKIES
    
    # Проверяем, ждём ли мы куки
    if not context.user_data.get('waiting_for_cookies', False):
        return
    
    text = update.message.text
    user_id = update.message.from_user.id
    
    # Парсим куки
    cookies = parse_cookies_from_text(text)
    
    if cookies and len(cookies) > 0:
        # Сохраняем куки
        X_COOKIES = cookies
        context.user_data['waiting_for_cookies'] = False
        
        # Показываем сколько кук загружено
        auth_token = next((c for c in cookies if c.get('name') == 'auth_token'), None)
        ct0 = next((c for c in cookies if c.get('name') == 'ct0'), None)
        twid = next((c for c in cookies if c.get('name') == 'twid'), None)
        
        add_log(f"✅ Загружено {len(cookies)} кук от пользователя {user_id}")
        
        await update.message.reply_text(
            f"✅ **Куки загружены!**\n\n"
            f"🍪 Всего кук: {len(cookies)}\n"
            f"🔑 auth_token: {'✅' if auth_token else '❌'}\n"
            f"🔐 ct0: {'✅' if ct0 else '❌'}\n"
            f"👤 twid: {'✅' if twid else '❌'}\n\n"
            f"Теперь можно:\n"
            f"1️⃣ Запустить браузер: /browserplay\n"
            f"2️⃣ Войти в X: /loginx\n"
            f"3️⃣ Посмотреть процесс: /watch_x",
            reply_markup=get_play_keyboard(),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "❌ **Не удалось распознать куки**\n\n"
            "Проверь формат. Должно быть:\n"
            "1️⃣ JSON массив: `[{\"name\":\"...\",\"value\":\"...\"}]`\n"
            "2️⃣ Строка: `name1=value1; name2=value2`\n"
            "3️⃣ Пары с новой строки\n\n"
            "Попробуй ещё раз или нажми ◀️ Назад",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Назад", callback_data="browser_back")]
            ])
        )

# === КОМАНДА WATCH_X (для кнопки) ===

async def watch_x_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Версия watch_x для callback"""
    global browser_started, browser, page
    
    query = update.callback_query
    
    if not X_COOKIES:
        await query.edit_message_text(
            "❌ **Нет кук!**\n\n"
            "Сначала вставь куки через кнопку 🍪 Вставить куки",
            reply_markup=get_play_keyboard()
        )
        return
    
    await query.edit_message_text(
        "🎬 **Начинаю демонстрацию входа на X**\n\n"
        "Бот покажет все шаги со скриншотами...",
        parse_mode='Markdown'
    )
    
    try:
        # Запускаем браузер, если не запущен
        if not browser_started:
            await query.edit_message_text("🚀 Запускаю браузер...")
            browser = await launch_async(
                headless=True,
                humanize=True,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
            page = await browser.new_page()
            browser_started = True
            await asyncio.sleep(2)
        
        # ШАГ 1: Открываем X.com
        await query.edit_message_text("1️⃣ Открываю X.com...")
        await page.goto(fix_url("x.com"), wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        await asyncio.sleep(2)
        
        screenshot1 = await page.screenshot(full_page=False, timeout=SCREENSHOT_TIMEOUT)
        await query.message.reply_photo(
            photo=screenshot1,
            caption="📸 ШАГ 1: Главная страница X (без входа)"
        )
        await asyncio.sleep(1)
        
        # ШАГ 2: Устанавливаем куки
        await query.edit_message_text("2️⃣ Устанавливаю куки для входа...")
        await page.context.add_cookies(X_COOKIES)
        await asyncio.sleep(2)
        
        cookies_after_set = await page.context.cookies()
        auth_token_set = next((c for c in cookies_after_set if c.get('name') == 'auth_token'), None)
        
        if auth_token_set:
            await query.edit_message_text("✅ auth_token установлен успешно!")
        else:
            await query.edit_message_text("❌ auth_token НЕ установлен!")
            return
        
        # ШАГ 3: Обновляем страницу
        await query.edit_message_text("3️⃣ Обновляю страницу с куками...")
        await page.reload(wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        await asyncio.sleep(3)
        
        screenshot2 = await page.screenshot(full_page=False, timeout=SCREENSHOT_TIMEOUT)
        await query.message.reply_photo(
            photo=screenshot2,
            caption="📸 ШАГ 2: После установки кук"
        )
        await asyncio.sleep(1)
        
        # ШАГ 4: Переходим на главную
        await query.edit_message_text("4️⃣ Перехожу на главную страницу X...")
        await page.goto(fix_url("x.com/home"), wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        await asyncio.sleep(3)
        
        screenshot3 = await page.screenshot(full_page=False, timeout=SCREENSHOT_TIMEOUT)
        
        cookies_after = await page.context.cookies()
        auth_token_after = next((c for c in cookies_after if c.get('name') == 'auth_token'), None)
        
        status_msg = "✅ ВХОД ВЫПОЛНЕН!" if auth_token_after else "❌ ВХОД НЕ УДАЛСЯ"
        
        await query.message.reply_photo(
            photo=screenshot3,
            caption=f"📸 ШАГ 3: Главная страница X\n\nСтатус: {status_msg}"
        )
        await asyncio.sleep(1)
        
        # ШАГ 5: Проверка
        await query.edit_message_text("5️⃣ Проверяю содержимое страницы...")
        
        has_tweets = await page.evaluate('''
            (function() {
                const tweets = document.querySelectorAll('[data-testid="tweet"]');
                return tweets.length > 0;
            })();
        ''')
        
        has_login = await page.evaluate('''
            (function() {
                const login = document.querySelector('[data-testid="login"]');
                const signup = document.querySelector('[data-testid="signup"]');
                return !!(login || signup);
            })();
        ''')
        
        await page.evaluate('window.scrollTo(0, 500)')
        await asyncio.sleep(1)
        screenshot4 = await page.screenshot(full_page=False, timeout=SCREENSHOT_TIMEOUT)
        
        await query.message.reply_photo(
            photo=screenshot4,
            caption=f"📸 ШАГ 4: Содержимое страницы\n\n"
                   f"📊 Твиты: {'Есть ✅' if has_tweets else 'Нет ❌'}\n"
                   f"🔐 Форма входа: {'Видна ❌' if has_login else 'Не видна ✅'}\n\n"
                   f"{'✅ Бот успешно вошёл в X!' if auth_token_after and has_tweets else '❌ Вход не удался. Обнови куки.'}"
        )
        
        if auth_token_after and has_tweets:
            await query.edit_message_text(
                "✅ **ВХОД В X УСПЕШЕН!**\n\n"
                "Теперь доступно: /tweet <текст>",
                reply_markup=get_play_keyboard(),
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                "❌ **ВХОД НЕ УДАЛСЯ**\n\n"
                "Обнови куки через 🍪 Вставить куки",
                reply_markup=get_play_keyboard(),
                parse_mode='Markdown'
            )
        
    except Exception as e:
        logger.error(f"Ошибка в watch_x: {e}")
        await query.edit_message_text(f"❌ Ошибка: {str(e)[:300]}", reply_markup=get_play_keyboard())

# === ОБЫЧНЫЕ КОМАНДЫ ===

async def watch_x(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /watch_x"""
    class FakeQuery:
        def __init__(self, message):
            self.message = message
        async def answer(self):
            pass
        async def edit_message_text(self, text, *args, **kwargs):
            return await self.message.reply_text(text, *args, **kwargs)
    
    fake_query = FakeQuery(update.message)
    update.callback_query = fake_query
    await watch_x_callback(update, context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🕵️ **Бот с CloakBrowser**\n\n"
        "📋 Команды:\n"
        "/browserplay - 🎮 Панель управления\n"
        "/watch_x - 🎬 Показать процесс входа в X\n"
        "/shot - 📸 Скриншот текущей страницы\n"
        "/shot <url> - 📸 Скриншот указанного URL\n"
        "/html <url> - 📄 Получить HTML\n"
        "/cookies <url> - 🍪 Показать куки\n"
        "/loginx - 🔐 Войти в X\n"
        "/tweet <текст> - 🐦 Опубликовать твит\n"
        "/status - 📊 Статус браузера\n\n"
        f"📦 CloakBrowser: {'✅ Установлен' if CLOAK_AVAILABLE else '❌ Не установлен'}\n"
        f"🍪 Кук загружено: {len(X_COOKIES)}",
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
        
        await page.goto(fix_url(url), wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        content = await page.content()
        preview = content[:4000] + "..." if len(content) > 4000 else content
        await update.message.reply_text(f"📄 HTML ({len(content)} символов):\n\n{preview}")
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

async def shot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global browser_started, browser, page
    
    # Если есть URL - переходим по нему
    if context.args:
        url = context.args[0]
        await update.message.reply_text(f"📸 Перехожу на {url} и делаю скриншот...")
        
        try:
            if not browser_started:
                browser = await launch_async(headless=True, humanize=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
                page = await browser.new_page()
                browser_started = True
            
            await page.goto(fix_url(url), wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
            screenshot = await page.screenshot(full_page=True, timeout=SCREENSHOT_TIMEOUT)
            await update.message.reply_photo(photo=screenshot, caption=f"📸 Скриншот: {url}")
            return
            
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
            return
    
    # Если URL не указан - скриншот текущей страницы
    if not browser_started:
        await update.message.reply_text("❌ Браузер не запущен! Сначала запусти: /browserplay")
        return
    
    if not page:
        await update.message.reply_text("❌ Страница не открыта! Открой страницу через /html или /shot <url>")
        return
    
    await update.message.reply_text("📸 Делаю скриншот текущей страницы...")
    
    try:
        current_url = page.url
        screenshot = await page.screenshot(full_page=True, timeout=SCREENSHOT_TIMEOUT)
        await update.message.reply_photo(
            photo=screenshot,
            caption=f"📸 Текущая страница: {current_url}"
        )
        
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
        
        await page.goto(fix_url(url), wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
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
    
    if not X_COOKIES:
        await update.message.reply_text(
            "❌ **Нет кук!**\n\n"
            "Сначала вставь куки через /browserplay → 🍪 Вставить куки"
        )
        return
    
    await update.message.reply_text("🔐 Выполняю вход в X...")
    
    try:
        if not browser_started:
            browser = await launch_async(headless=True, humanize=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            page = await browser.new_page()
            browser_started = True
        
        await page.context.add_cookies(X_COOKIES)
        await page.goto(fix_url("x.com/home"), wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        
        cookies_after = await page.context.cookies()
        auth_cookie = next((c for c in cookies_after if c.get('name') == 'auth_token'), None)
        
        if auth_cookie:
            add_log("✅ Успешный вход в X через /loginx")
            screenshot = await page.screenshot(full_page=False, timeout=SCREENSHOT_TIMEOUT)
            await update.message.reply_photo(
                photo=screenshot,
                caption="✅ Успешный вход в X!\n\nТеперь доступно: /tweet <текст>"
            )
        else:
            await update.message.reply_text(
                "❌ Авторизация не удалась. Обнови куки.\n\n"
                "Используй /browserplay → 🍪 Вставить куки"
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
        
        await page.goto(fix_url("x.com/compose/post"), wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
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
            screenshot = await page.screenshot(timeout=SCREENSHOT_TIMEOUT)
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
        f"🍪 Кук загружено: {len(X_COOKIES)}\n"
        f"📝 Логов: {len(setup_logs)}\n"
        f"🕒 Последний лог: {setup_logs[-1] if setup_logs else 'Нет'}",
        parse_mode='Markdown'
    )

# === ЗАПУСК ===

def main():
    app = Application.builder().token(TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("browserplay", browserplay))
    app.add_handler(CommandHandler("watch_x", watch_x))
    app.add_handler(CommandHandler("html", html_command))
    app.add_handler(CommandHandler("shot", shot_command))
    app.add_handler(CommandHandler("cookies", cookies_command))
    app.add_handler(CommandHandler("loginx", loginx))
    app.add_handler(CommandHandler("tweet", tweet_command))
    app.add_handler(CommandHandler("status", status_command))
    
    # Callback для кнопок
    app.add_handler(CallbackQueryHandler(handle_play_callback, pattern="^browser_"))
    
    # Обработчик сообщений (для ввода кук)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookies_input))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()