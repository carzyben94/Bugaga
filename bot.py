import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Импортируем все функции из pydoll_handlers
from pydoll_handlers import (
    # Базовые функции
    search_and_screenshot,
    get_page_title,
    execute_javascript,
    take_screenshot_of_element,
    find_in_shadow_dom,
    find_all_shadow_roots,
    load_page_without_images,
    record_har,
    save_page_bundle,
    human_click_example,
    concurrent_scraping,
    extract_quotes,
    # X.com функции
    post_tweet,
    reply_to_tweet,
    like_tweet,
    retweet_tweet,
    get_profile,
    get_timeline,
    search_tweets,
    follow_user,
    unfollow_user
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения")

# ============================================================
# ОБРАБОТЧИКИ КОМАНД
# ============================================================

# ---------- СТАРТ ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение со списком команд"""
    await update.message.reply_text(
        "👋 Привет! Я бот с **полным функционалом Pydoll**.\n\n"
        "📌 **Основные команды:**\n"
        "/start - Показать это сообщение\n"
        "/search <запрос> - Поиск в Google со скриншотом\n"
        "/title <url> - Получить заголовок страницы\n"
        "/js <url> <script> - Выполнить JavaScript\n"
        "/element <url> <селектор> - Скриншот элемента\n\n"
        "📌 **Расширенные команды:**\n"
        "/shadow <url> <хост> <внутренний> - Поиск в Shadow DOM\n"
        "/shadows <url> - Найти все Shadow Roots\n"
        "/block <url> - Загрузить страницу без картинок\n"
        "/har <url> - Записать HAR-лог\n"
        "/bundle <url> - Сохранить страницу в ZIP\n"
        "/human <url> <селектор> - Клик с humanize=True\n"
        "/concurrent <url1> <url2> ... - Параллельная загрузка\n"
        "/parse <url> - Парсинг цитат (ExtractionModel)\n"
        "/hybrid <login_url> <user> <pass> <api_url> - Гибридная автоматизация\n\n"
        "🐦 **Команды для X.com (авторизация через куки):**\n"
        "/tweet <текст> - Опубликовать твит\n"
        "/reply <url> <текст> - Ответить на твит\n"
        "/like <url> - Поставить лайк\n"
        "/retweet <url> - Сделать ретвит\n"
        "/profile <username> - Информация о профиле\n"
        "/timeline <username> [количество] - Последние твиты\n"
        "/search_tweets <запрос> [количество] - Поиск твитов\n"
        "/follow <username> - Подписаться\n"
        "/unfollow <username> - Отписаться"
    )

# ---------- БАЗОВЫЕ КОМАНДЫ ----------
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск в Google со скриншотом"""
    if not context.args:
        await update.message.reply_text("❌ Использование: /search <запрос>")
        return
    
    query = " ".join(context.args)
    await update.message.reply_text(f"🔍 Ищу: {query}...")
    
    try:
        screenshot_path = await search_and_screenshot(query)
        
        with open(screenshot_path, 'rb') as photo:
            await update.message.reply_photo(
                photo,
                caption=f"✅ Результат поиска: {query}"
            )
        
        os.remove(screenshot_path)
        
    except Exception as e:
        logger.error(f"Ошибка в search: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить заголовок страницы"""
    if not context.args:
        await update.message.reply_text("❌ Использование: /title <url>")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"📄 Загружаю: {url}...")
    
    try:
        page_title = await get_page_title(url)
        await update.message.reply_text(f"📌 Заголовок: {page_title}")
    except Exception as e:
        logger.error(f"Ошибка в title: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def js(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнить JavaScript на странице"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ Использование: /js <url> <script>")
        return
    
    url = context.args[0]
    script = " ".join(context.args[1:])
    
    try:
        result = await execute_javascript(url, script)
        await update.message.reply_text(f"✅ Результат JS:\n{result[:500]}")
    except Exception as e:
        logger.error(f"Ошибка в js: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def element_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скриншот элемента по CSS-селектору"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ Использование: /element <url> <css_selector>")
        return
    
    url = context.args[0]
    selector = context.args[1]
    
    try:
        screenshot_path = await take_screenshot_of_element(url, selector)
        
        with open(screenshot_path, 'rb') as photo:
            await update.message.reply_photo(
                photo,
                caption=f"✅ Элемент: {selector}"
            )
        
        os.remove(screenshot_path)
        
    except Exception as e:
        logger.error(f"Ошибка в element_screenshot: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

# ---------- РАСШИРЕННЫЕ КОМАНДЫ ----------
async def shadow_dom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск элемента внутри Shadow DOM"""
    if len(context.args) < 3:
        await update.message.reply_text("❌ Использование: /shadow <url> <host_selector> <inner_selector>")
        return
    
    url = context.args[0]
    host_selector = context.args[1]
    inner_selector = context.args[2]
    
    try:
        text = await find_in_shadow_dom(url, host_selector, inner_selector)
        await update.message.reply_text(f"✅ Найдено в Shadow DOM:\n{text[:500]}")
    except Exception as e:
        logger.error(f"Ошибка в shadow_dom: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def all_shadows(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Найти все Shadow Roots на странице"""
    if not context.args:
        await update.message.reply_text("❌ Использование: /shadows <url>")
        return
    
    url = context.args[0]
    
    try:
        results = await find_all_shadow_roots(url)
        await update.message.reply_text(f"✅ Найдено Shadow Roots: {len(results)}")
    except Exception as e:
        logger.error(f"Ошибка в all_shadows: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def block_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Загрузить страницу без картинок"""
    if not context.args:
        await update.message.reply_text("❌ Использование: /block <url>")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"🚫 Загружаю без картинок: {url}...")
    
    try:
        screenshot_path = await load_page_without_images(url)
        
        with open(screenshot_path, 'rb') as photo:
            await update.message.reply_photo(
                photo,
                caption="✅ Страница загружена без картинок и стилей"
            )
        
        os.remove(screenshot_path)
        
    except Exception as e:
        logger.error(f"Ошибка в block_images: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def har_recording(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Записать HAR-лог"""
    if not context.args:
        await update.message.reply_text("❌ Использование: /har <url>")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"📊 Записываю HAR для: {url}...")
    
    try:
        result = await record_har(url)
        await update.message.reply_text(
            f"✅ Записано {result['entries_count']} запросов\n"
            f"📁 Файл: {result['file_path']}"
        )
    except Exception as e:
        logger.error(f"Ошибка в har_recording: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def page_bundle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранить страницу в ZIP"""
    if not context.args:
        await update.message.reply_text(
            "❌ Использование: /bundle <url>\n"
            "Добавьте --inline для встраивания ресурсов"
        )
        return
    
    inline = "--inline" in context.args
    url = context.args[0] if not context.args[0].startswith("--") else context.args[1]
    
    await update.message.reply_text(f"📦 Сохраняю страницу: {url}...")
    
    try:
        bundle_path = await save_page_bundle(url, inline=inline)
        await update.message.reply_text(
            f"✅ Страница сохранена\n"
            f"📁 Файл: {bundle_path}"
        )
    except Exception as e:
        logger.error(f"Ошибка в page_bundle: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def human_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Клик с человеко-подобным движением мыши"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ Использование: /human <url> <css_selector>")
        return
    
    url = context.args[0]
    selector = context.args[1]
    
    try:
        screenshot_path = await human_click_example(url, selector)
        
        with open(screenshot_path, 'rb') as photo:
            await update.message.reply_photo(
                photo,
                caption=f"✅ Клик с humanize=True на {selector}"
            )
        
        os.remove(screenshot_path)
        
    except Exception as e:
        logger.error(f"Ошибка в human_click: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def concurrent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Параллельная загрузка нескольких страниц"""
    if not context.args:
        await update.message.reply_text("❌ Использование: /concurrent <url1> <url2> ...")
        return
    
    urls = context.args
    await update.message.reply_text(f"🔄 Загружаю {len(urls)} страниц параллельно...")
    
    try:
        results = await concurrent_scraping(urls)
        
        message = "📌 Результаты:\n\n"
        for i, (url, title) in enumerate(zip(urls, results), 1):
            message += f"{i}. {title[:50]}\n"
        
        await update.message.reply_text(message[:4000])
        
    except Exception as e:
        logger.error(f"Ошибка в concurrent: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Парсинг цитат с использованием ExtractionModel"""
    if not context.args:
        await update.message.reply_text("❌ Использование: /parse <url>")
        return
    
    url = context.args[0]
    await update.message.reply_text(f"🔍 Парсинг цитат: {url}...")
    
    try:
        quotes = await extract_quotes(url)
        
        if not quotes:
            await update.message.reply_text("❌ Цитаты не найдены")
            return
        
        message = f"📚 Найдено цитат: {len(quotes)}\n\n"
        for i, q in enumerate(quotes[:5], 1):
            text = q['text'][:50] + "..." if len(q['text']) > 50 else q['text']
            message += f"{i}. \"{text}\" — {q['author']}\n"
        
        if len(quotes) > 5:
            message += f"\n... и ещё {len(quotes) - 5} цитат"
        
        await update.message.reply_text(message[:4000])
        
    except Exception as e:
        logger.error(f"Ошибка в parse: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def hybrid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Гибридная автоматизация (UI + API)"""
    if len(context.args) < 4:
        await update.message.reply_text(
            "❌ Использование: /hybrid <login_url> <username> <password> <api_url>"
        )
        return
    
    login_url = context.args[0]
    username = context.args[1]
    password = context.args[2]
    api_url = context.args[3]
    
    await update.message.reply_text("🔄 Выполняю гибридную автоматизацию...")
    
    try:
        result = await hybrid_automation_example(login_url, username, password, api_url)
        
        await update.message.reply_text(
            f"✅ Статус: {result['status']}\n"
            f"📊 Данные:\n{result['data'][:500]}"
        )
    except Exception as e:
        logger.error(f"Ошибка в hybrid: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

# ---------- X.COM КОМАНДЫ ----------
async def tweet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Опубликовать твит"""
    if not context.args:
        await update.message.reply_text("❌ /tweet <текст твита>")
        return
    
    text = " ".join(context.args)
    await update.message.reply_text(f"🐦 Публикую твит...")
    
    try:
        result = await post_tweet(text)
        if result:
            await update.message.reply_text(f"✅ Твит опубликован!\n\n{text[:200]}")
        else:
            await update.message.reply_text("❌ Ошибка публикации. Проверь куки.")
    except Exception as e:
        logger.error(f"Ошибка в tweet: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответить на твит"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ /reply <url_твита> <текст_ответа>")
        return
    
    tweet_url = context.args[0]
    text = " ".join(context.args[1:])
    
    await update.message.reply_text(f"💬 Отвечаю на твит...")
    
    try:
        result = await reply_to_tweet(tweet_url, text)
        if result:
            await update.message.reply_text(f"✅ Ответ опубликован!")
        else:
            await update.message.reply_text("❌ Ошибка ответа. Проверь куки.")
    except Exception as e:
        logger.error(f"Ошибка в reply: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def like(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поставить лайк"""
    if not context.args:
        await update.message.reply_text("❌ /like <url_твита>")
        return
    
    tweet_url = context.args[0]
    await update.message.reply_text(f"❤️ Ставлю лайк...")
    
    try:
        result = await like_tweet(tweet_url)
        if result:
            await update.message.reply_text(f"✅ Лайк поставлен!")
        else:
            await update.message.reply_text("❌ Ошибка. Проверь куки.")
    except Exception as e:
        logger.error(f"Ошибка в like: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def retweet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сделать ретвит"""
    if not context.args:
        await update.message.reply_text("❌ /retweet <url_твита>")
        return
    
    tweet_url = context.args[0]
    await update.message.reply_text(f"🔄 Делаю ретвит...")
    
    try:
        result = await retweet_tweet(tweet_url)
        if result:
            await update.message.reply_text(f"✅ Ретвит сделан!")
        else:
            await update.message.reply_text("❌ Ошибка. Проверь куки.")
    except Exception as e:
        logger.error(f"Ошибка в retweet: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить информацию о профиле"""
    if not context.args:
        await update.message.reply_text("❌ /profile <username>")
        return
    
    username = context.args[0].replace('@', '')
    await update.message.reply_text(f"👤 Загружаю профиль @{username}...")
    
    try:
        profile_data = await get_profile(username)
        
        if not profile_data:
            await update.message.reply_text("❌ Профиль не найден или нет авторизации")
            return
        
        message = f"👤 **{profile_data.get('name', '')}**\n"
        message += f"🔹 @{profile_data.get('username', '')}\n\n"
        message += f"📝 {profile_data.get('bio', 'Нет описания')[:200]}\n\n"
        message += f"📍 {profile_data.get('location', '')}\n"
        message += f"📅 Присоединился: {profile_data.get('joined', '')}\n"
        message += f"👥 Подписчики: {profile_data.get('followers', '')}\n"
        message += f"📌 Подписки: {profile_data.get('following', '')}"
        
        await update.message.reply_text(message)
        
    except Exception as e:
        logger.error(f"Ошибка в profile: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def timeline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить последние твиты пользователя"""
    if not context.args:
        await update.message.reply_text("❌ /timeline <username> [количество]")
        return
    
    username = context.args[0].replace('@', '')
    limit = int(context.args[1]) if len(context.args) > 1 else 5
    
    await update.message.reply_text(f"📊 Получаю твиты @{username}...")
    
    try:
        tweets = await get_timeline(username, limit)
        
        if not tweets:
            await update.message.reply_text("❌ Твиты не найдены или нет авторизации")
            return
        
        message = f"📊 Последние {len(tweets)} твитов @{username}:\n\n"
        for i, t in enumerate(tweets, 1):
            text = t.get('text', '')[:100]
            if len(t.get('text', '')) > 100:
                text += "..."
            message += f"{i}. ❤️ {t.get('likes', '0')} | 🔁 {t.get('retweets', '0')}\n"
            message += f"   {text}\n\n"
        
        await update.message.reply_text(message[:4000])
        
    except Exception as e:
        logger.error(f"Ошибка в timeline: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def search_tweets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск твитов по запросу"""
    if not context.args:
        await update.message.reply_text("❌ /search_tweets <запрос> [количество]")
        return
    
    query = context.args[0]
    limit = int(context.args[1]) if len(context.args) > 1 else 5
    
    await update.message.reply_text(f"🔍 Ищу твиты: {query}...")
    
    try:
        tweets = await search_tweets(query, limit)
        
        if not tweets:
            await update.message.reply_text("❌ Твиты не найдены или нет авторизации")
            return
        
        message = f"🔍 Результаты поиска: {query}\n\n"
        for i, t in enumerate(tweets, 1):
            text = t.get('text', '')[:100]
            if len(t.get('text', '')) > 100:
                text += "..."
            message += f"{i}. @{t.get('author_username', '')}: {text}\n"
            message += f"   ❤️ {t.get('likes', '0')} | 🔁 {t.get('retweets', '0')}\n\n"
        
        await update.message.reply_text(message[:4000])
        
    except Exception as e:
        logger.error(f"Ошибка в search_tweets_command: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def follow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подписаться на пользователя"""
    if not context.args:
        await update.message.reply_text("❌ /follow <username>")
        return
    
    username = context.args[0].replace('@', '')
    await update.message.reply_text(f"➕ Подписываюсь на @{username}...")
    
    try:
        result = await follow_user(username)
        if result:
            await update.message.reply_text(f"✅ Подписан на @{username}")
        else:
            await update.message.reply_text("❌ Ошибка подписки. Проверь куки.")
    except Exception as e:
        logger.error(f"Ошибка в follow: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

async def unfollow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отписаться от пользователя"""
    if not context.args:
        await update.message.reply_text("❌ /unfollow <username>")
        return
    
    username = context.args[0].replace('@', '')
    await update.message.reply_text(f"➖ Отписываюсь от @{username}...")
    
    try:
        result = await unfollow_user(username)
        if result:
            await update.message.reply_text(f"✅ Отписан от @{username}")
        else:
            await update.message.reply_text("❌ Ошибка отписки. Проверь куки.")
    except Exception as e:
        logger.error(f"Ошибка в unfollow: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")

# ============================================================
# ЗАПУСК БОТА
# ============================================================

def main():
    """Запуск бота"""
    logger.info("🚀 Запуск бота с полным функционалом Pydoll и поддержкой X.com...")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # ---------- БАЗОВЫЕ КОМАНДЫ ----------
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("title", title))
    app.add_handler(CommandHandler("js", js))
    app.add_handler(CommandHandler("element", element_screenshot))
    
    # ---------- РАСШИРЕННЫЕ КОМАНДЫ ----------
    app.add_handler(CommandHandler("shadow", shadow_dom))
    app.add_handler(CommandHandler("shadows", all_shadows))
    app.add_handler(CommandHandler("block", block_images))
    app.add_handler(CommandHandler("har", har_recording))
    app.add_handler(CommandHandler("bundle", page_bundle))
    app.add_handler(CommandHandler("human", human_click))
    app.add_handler(CommandHandler("concurrent", concurrent))
    app.add_handler(CommandHandler("parse", parse))
    app.add_handler(CommandHandler("hybrid", hybrid))
    
    # ---------- X.COM КОМАНДЫ ----------
    app.add_handler(CommandHandler("tweet", tweet))
    app.add_handler(CommandHandler("reply", reply))
    app.add_handler(CommandHandler("like", like))
    app.add_handler(CommandHandler("retweet", retweet))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("timeline", timeline))
    app.add_handler(CommandHandler("search_tweets", search_tweets_command))
    app.add_handler(CommandHandler("follow", follow))
    app.add_handler(CommandHandler("unfollow", unfollow))
    
    # Запускаем поллинг
    logger.info("✅ Бот запущен, ожидаем сообщения...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()